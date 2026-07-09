"""Characterization tests for the run_agent v1 handler's restart/restore behavior.

These tests pin the behavior of the replay scan (``scan_message_history`` in
``setup.py``), the dedup walk (``_drop_already_processed_messages``), and the
dispatch/orphan-synthesis logic in ``_run_agent_in_environment`` (``v1.py``), so
that changes to restart/restore semantics are explicit and deliberate rather
than accidental. A failing scenario means "this behavior changed"; a change must
then either be accepted on purpose or treated as a regression to fix.

Most scenarios drive the loop with explicit queue contents (``re_queued_messages``
/ ``input_message_queue``), pinning loop behavior independently of what the
production dedup path would put in the queue. Where the production path matters,
the scenario asserts on the scan's derived cursor directly.

Fixture vocabulary shared across these tests:
- "chat": a persisted ``ChatInputUserMessage`` plus its
  ``RequestStartedAgentMessage(request_id=chat.message_id)``.
- "partial": a ``ResponseBlockAgentMessage`` persisted after the chat's
  ``RequestStarted`` (Claude produced visible output before the run ended).
- "answer": a persisted ``UserQuestionAnswerMessage`` plus its own
  ``RequestStartedAgentMessage``.
- "cursor": ``HistoryScan.last_processed_message_id``, derived from the persisted
  message log by ``scan_message_history`` -- there is no stored cursor. The loop
  does not branch on it; it feeds ``_drop_already_processed_messages`` on the
  production path.
"""

import threading
from queue import Queue
from unittest.mock import patch

import pytest
from pydantic import PrivateAttr

from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.common import generate_id
from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.state.messages import Message
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.tasks.handlers.run_agent.setup import HistoryScan
from sculptor.tasks.handlers.run_agent.setup import _drop_already_processed_messages
from sculptor.tasks.handlers.run_agent.setup import scan_message_history
from sculptor.tasks.handlers.run_agent.v1 import AgentPaused
from sculptor.tasks.handlers.run_agent.v1 import _run_agent_in_environment


def _set_task_state(task: Task, state: AgentTaskStateV2, services: ServiceCollectionForTask) -> None:
    """Store current_state on a task in the database."""
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task.object_id)
        assert task_row is not None
        updated = task_row.evolve(task_row.ref().current_state, state.model_dump())
        transaction.upsert_task(updated)


def _scan_history(local_task: Task, services: ServiceCollectionForTask) -> HistoryScan:
    """Fetch the task's saved messages and scan them, as run_agent_task_v1 does."""
    with services.data_model_service.open_task_transaction() as transaction:
        saved_messages = services.task_service.get_saved_messages_for_task(local_task.object_id, transaction)
    return scan_message_history(saved_messages)


def _make_in_flight_chat_message() -> ChatInputUserMessage:
    return ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Long prompt",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )


def _make_partial_response_block() -> ResponseBlockAgentMessage:
    return ResponseBlockAgentMessage(
        message_id=AgentMessageID(),
        role="assistant",
        assistant_message_id=AssistantMessageID(generate_id()),
        content=(TextBlock(text="I'll start by..."),),
    )


def _persist_messages(local_task: Task, services: ServiceCollectionForTask, messages: list[MessageTypes]) -> None:
    """Persist ``messages`` in order, one transaction per message.

    Per-message transactions mirror how the real flows write (API save, then the
    loop's _save_messages batches).
    """
    for message in messages:
        with services.data_model_service.open_task_transaction() as transaction:
            services.task_service.create_message(message, local_task.object_id, transaction)


def _make_sigterm_error() -> SerializedException:
    """Build a serialized AgentClientError with a SIGTERM exit code -- a "killed" completion."""
    try:
        raise AgentClientError("Killed by SIGTERM", exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)
    except AgentClientError as exc:
        return SerializedException.build(exc, exc.__traceback__)


def _make_non_killed_error(exit_code: int) -> SerializedException:
    """Build a serialized AgentClientError whose exit code is not a SIGTERM/SIGINT code."""
    try:
        raise AgentClientError("Agent exited with an error", exit_code=exit_code)
    except AgentClientError as exc:
        return SerializedException.build(exc, exc.__traceback__)


def _assert_no_synthesized_settlement(
    local_task: Task, services: ServiceCollectionForTask, request_id: AgentMessageID
) -> None:
    """No RequestSuccess(turn_abandoned=True) was persisted for ``request_id``.

    ``turn_abandoned=True`` is the marker the orphan-synthesis code in v1.py always
    sets, so its absence means the loop did not treat this request as a settled
    orphan.
    """
    with services.data_model_service.open_task_transaction() as transaction:
        saved_messages = services.task_service.get_saved_messages_for_task(local_task.object_id, transaction)
    synthesized = [
        m
        for m in saved_messages
        if isinstance(m, RequestSuccessAgentMessage) and m.request_id == request_id and m.turn_abandoned
    ]
    assert synthesized == [], f"expected no synthesized settlement for {request_id}, got {synthesized}"


class _RecordOnlyAgent(DefaultAgentWrapper):
    """Fake agent that records pushed chat/resume messages without doing real work.

    On ``StopAgentUserMessage`` (which the v1 loop pushes when it observes
    ``shutdown_event``), the agent emits ``RequestStoppedAgentMessage`` for the most
    recent chat/resume message and sets ``_exit_code = SIGTERM`` so the next loop
    iteration early-returns into ``_handle_completed_agent`` via the poll() check.
    Requires a chat/resume message to have been pushed before Stop arrives.
    """

    _pushed_chat_or_resume: list[ChatInputUserMessage | ResumeAgentResponseRunnerMessage] = PrivateAttr(
        default_factory=list
    )
    _last_chat_message_id: AgentMessageID | None = PrivateAttr(default=None)

    def _start(self) -> None: ...

    def _terminate(self, force_kill_seconds: float) -> None: ...

    def wait(self, timeout: float) -> int:
        return self._exit_code if self._exit_code is not None else 0

    @property
    def pushed_chat_or_resume(self) -> list[ChatInputUserMessage | ResumeAgentResponseRunnerMessage]:
        return self._pushed_chat_or_resume

    def _push_message(self, message: Message) -> bool:
        if isinstance(message, ChatInputUserMessage):
            self._pushed_chat_or_resume.append(message)
            self._last_chat_message_id = message.message_id
            return True
        if isinstance(message, ResumeAgentResponseRunnerMessage):
            self._pushed_chat_or_resume.append(message)
            self._last_chat_message_id = message.for_user_message_id
            return True
        if isinstance(message, StopAgentUserMessage):
            chat_id = self._last_chat_message_id
            assert chat_id is not None, "Stop arrived before any chat/resume message"
            self._output_messages.put(
                RequestStoppedAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=chat_id,
                    error=_make_sigterm_error(),
                )
            )
            self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
            return True
        return False


class _RecordingIdleStopAgent(DefaultAgentWrapper):
    """Fake agent that records every message pushed to it and treats
    ``StopAgentUserMessage`` as an immediate SIGTERM exit, without requiring any
    chat/resume/answer push to precede it.

    Used for empty-queue (no-op resume) scenarios, where Stop may be the only
    message ever pushed -- or may even arrive before a message already sitting in
    ``input_message_queue``, since the loop's shutdown check runs before it
    dispatches messages drained from that queue in the same iteration.
    """

    _pushed: list[Message] = PrivateAttr(default_factory=list)

    def _start(self) -> None: ...

    def _terminate(self, force_kill_seconds: float) -> None: ...

    def wait(self, timeout: float) -> int:
        return self._exit_code if self._exit_code is not None else 0

    @property
    def pushed(self) -> list[Message]:
        return self._pushed

    def _push_message(self, message: Message) -> bool:
        self._pushed.append(message)
        if isinstance(message, StopAgentUserMessage):
            self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
        return True


def test_queued_inflight_chat_with_partial_is_resumed_not_synthesized(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A queued in-flight chat message with a partial response and no completion
    is resumed, not synthesized as a settled orphan.

    Orphan synthesis (see the killed-stop-with-empty-queue scenario) only fires
    when there is nothing left in the queue to drive a resume. Here the chat
    message is still in ``re_queued_messages``, so the replay scan's in-flight
    tracking survives to the pre-loop send and converts the push into a
    ``ResumeAgentResponseRunnerMessage`` instead.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordOnlyAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert len(fake_agent.pushed_chat_or_resume) == 1, (
        f"expected exactly one chat/resume push, got {fake_agent.pushed_chat_or_resume}"
    )
    first_push = fake_agent.pushed_chat_or_resume[0]
    assert isinstance(first_push, ResumeAgentResponseRunnerMessage), (
        f"expected a resume, got {type(first_push).__name__}"
    )
    assert first_push.for_user_message_id == chat_message.message_id

    _assert_no_synthesized_settlement(local_task, services, chat_message.message_id)


def test_queued_inflight_chat_without_partial_is_resent_raw(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A queued in-flight chat message with NO partial response and no completion
    is resent as a fresh raw chat message, not a resume.

    With no visible output to continue from, the replay scan's end-of-loop
    ``is_partial_agent_response`` check clears the in-flight id, so
    ``_send_user_input_message`` falls through to pushing the original message
    as-is instead of converting it to a resume.

    This pins the loop's behavior GIVEN a queued message. On the production
    path the derivation settles this shape (it is dropped, not queued) and the
    dangling request is terminalized by the orphan synthesis instead — see
    ``test_crash_before_any_output_with_empty_queue_synthesizes_settlement``
    in v1_test.py. The raw-resend path remains reachable when the message is
    explicitly re-queued (e.g. a Stop-triggered re-queue).
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordOnlyAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert len(fake_agent.pushed_chat_or_resume) == 1, (
        f"expected exactly one chat/resume push, got {fake_agent.pushed_chat_or_resume}"
    )
    first_push = fake_agent.pushed_chat_or_resume[0]
    assert isinstance(first_push, ChatInputUserMessage), f"expected a raw resend, got {type(first_push).__name__}"
    assert first_push.message_id == chat_message.message_id

    _assert_no_synthesized_settlement(local_task, services, chat_message.message_id)


def test_user_stopped_turn_is_settled_no_redelivery_no_synthesis(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A user-initiated stop (a plain interrupted, non-abandoned RequestSuccess)
    settles the chat message: the derived cursor lands on it, and with an empty
    queue the loop performs no redelivery and no synthesis. This is the everyday
    "user clicked stop" shape, the dominant restart path.

    The persisted completion here is a RequestSuccess, not a
    RequestStoppedAgentMessage, so the replay scan's ``get_killed_exit_code``
    check (which only special-cases RequestStoppedAgentMessage) never applies to
    it -- the completion unconditionally clears the in-flight tracking on sight,
    settling the turn without needing ``turn_abandoned=True``.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            RequestSuccessAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                interrupted=True,
                turn_abandoned=False,
            ),
        ],
    )

    # The production path settles the chat message via the derived cursor, so it
    # is dropped from the replayed queue before the loop ever sees it.
    assert _scan_history(local_task, services).last_processed_message_id == chat_message.message_id

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordingIdleStopAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert len(fake_agent.pushed) == 1, f"expected only the Stop to be pushed, got {fake_agent.pushed}"
    assert isinstance(fake_agent.pushed[0], StopAgentUserMessage)

    _assert_no_synthesized_settlement(local_task, services, chat_message.message_id)


def test_killed_stop_with_partial_and_empty_queue_synthesizes_settlement(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """The original SCU-1559 stuck shape: a killed (SIGTERM) stop leaves the chat
    message's in-flight tracking alive across replay, and with no pending message
    to drive a resume, the no-op-resume path synthesizes exactly one
    interrupted+turn_abandoned RequestSuccess so the frontend settles instead of
    sticking on "thinking" forever.

    ``get_killed_exit_code`` recognizes the SIGTERM exit code on the persisted
    ``RequestStoppedAgentMessage``, so the replay scan's completion-clearing branch
    treats it as "not really done" and keeps ``in_flight_chat_message_id`` set --
    unlike a plain RequestSuccess (see the user-stopped-turn scenario), which
    always clears it.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                error=_make_sigterm_error(),
            ),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordingIdleStopAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    with services.data_model_service.open_task_transaction() as transaction:
        saved_messages = services.task_service.get_saved_messages_for_task(local_task.object_id, transaction)

    synthesized = [
        m
        for m in saved_messages
        if isinstance(m, RequestSuccessAgentMessage) and m.request_id == chat_message.message_id and m.turn_abandoned
    ]
    assert len(synthesized) == 1, f"expected exactly one synthesized settlement, got {synthesized}"
    assert synthesized[0].interrupted is True

    # The synthesized completion settles the chat message for the next restart's
    # derived cursor, so it will be dropped rather than re-queued.
    assert scan_message_history(saved_messages).last_processed_message_id == chat_message.message_id


def test_killed_stop_with_partial_and_queued_chat_is_resumed_not_synthesized(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """Same killed-stop history as the empty-queue scenario, but the chat message
    is still queued -- which is what the production path produces here, since a
    killed stop keeps the message in flight and the derived cursor never settles
    an in-flight message. Being queued takes priority over synthesis: the loop
    resumes the message instead of settling it with a synthesized completion.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                error=_make_sigterm_error(),
            ),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordOnlyAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert len(fake_agent.pushed_chat_or_resume) == 1, (
        f"expected exactly one chat/resume push, got {fake_agent.pushed_chat_or_resume}"
    )
    first_push = fake_agent.pushed_chat_or_resume[0]
    assert isinstance(first_push, ResumeAgentResponseRunnerMessage), (
        f"expected a resume, got {type(first_push).__name__}"
    )
    assert first_push.for_user_message_id == chat_message.message_id

    _assert_no_synthesized_settlement(local_task, services, chat_message.message_id)


def test_marked_completion_derives_cursor_and_drops_message(
    local_task: Task,
    services: ServiceCollectionForTask,
) -> None:
    """A turn_abandoned completion settles the chat message in the derived
    cursor, and that cursor drops the now-settled message from a replayed queue.

    This is the persisted shape the orphan-synthesis path leaves behind: the
    synthesized turn_abandoned completion is the only record that the request was
    terminally settled. The derivation must count it (in-flight tracking clears
    on the completion), and the derived cursor must be usable by
    ``_drop_already_processed_messages`` without raising or re-queuing the
    already-settled message.
    """
    chat_message = _make_in_flight_chat_message()

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            RequestSuccessAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                interrupted=True,
                turn_abandoned=True,
            ),
        ],
    )

    scan = _scan_history(local_task, services)

    assert scan.last_processed_message_id == chat_message.message_id, (
        "the derived cursor must settle on the turn_abandoned completion's request id"
    )

    replay_queue: Queue = Queue()
    replay_queue.put(chat_message)
    dropped, re_queued = _drop_already_processed_messages(scan.last_processed_message_id, replay_queue)

    assert dropped == (chat_message,)
    assert re_queued == ()
    assert replay_queue.empty()


def test_unmarked_interrupted_completion_settles_derivation_but_redelivers_raw_if_queued(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A plain interrupted (non-abandoned) RequestSuccess for the in-flight chat
    message clears the replay scan's in-flight tracking the same as a clean
    completion would. On the production path that settles the message in the
    derived cursor, so dedup drops it before it ever reaches the queue -- it is
    neither resumed nor re-delivered. At the loop level, if such a message IS
    handed to the loop as queued input, it is re-delivered as a fresh raw chat
    message, not resumed, even though a partial response exists to resume from
    (the cleared in-flight tracking is what would have converted it to a resume).

    ``get_killed_exit_code`` only special-cases ``RequestStoppedAgentMessage``, so
    any ``RequestSuccessAgentMessage`` -- even ``interrupted=True,
    turn_abandoned=False``, which ``RequestSuccessAgentMessage``'s own docstring
    says means "the turn may still be resumed" -- clears
    ``in_flight_chat_message_id``. This is the opposite of how an orphaned
    ANSWER's interrupted, non-abandoned completion is treated (see
    ``test_orphaned_answer_with_interrupted_completion_is_still_resumed`` in
    v1_test.py, which keeps the answer orphaned and resumable): the chat and
    answer completion-clearing conditions in the replay scan are not symmetric.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            RequestSuccessAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                interrupted=True,
                turn_abandoned=False,
            ),
        ],
    )

    # Production path: the interrupted completion settles the chat message, so
    # the derived cursor drops it from the replayed queue.
    assert _scan_history(local_task, services).last_processed_message_id == chat_message.message_id

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordOnlyAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert len(fake_agent.pushed_chat_or_resume) == 1, (
        f"expected exactly one chat/resume push, got {fake_agent.pushed_chat_or_resume}"
    )
    first_push = fake_agent.pushed_chat_or_resume[0]
    assert isinstance(first_push, ChatInputUserMessage), (
        f"pin: an interrupted-but-not-abandoned completion still clears in-flight tracking, forcing raw redelivery instead of resume; got {type(first_push).__name__}"
    )
    assert first_push.message_id == chat_message.message_id

    _assert_no_synthesized_settlement(local_task, services, chat_message.message_id)


def test_nonkilled_stop_is_terminal_no_synthesis(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A RequestStoppedAgentMessage whose error is NOT a SIGTERM/SIGINT exit code
    is treated as a genuine terminal stop, not a kill: ``get_killed_exit_code``
    returns 0 for it, so the replay scan clears the in-flight chat tracking the
    same as any other completion -- the derived cursor settles the message. With
    no pending message, there is nothing left to synthesize -- unlike the
    killed-stop shape, which keeps the in-flight id alive and does synthesize.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                error=_make_non_killed_error(exit_code=1),
            ),
        ],
    )

    # The non-killed stop settles the chat message in the derived cursor, which
    # is why the production path arrives here with nothing queued.
    assert _scan_history(local_task, services).last_processed_message_id == chat_message.message_id

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordingIdleStopAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert len(fake_agent.pushed) == 1, f"expected only the Stop to be pushed, got {fake_agent.pushed}"
    assert isinstance(fake_agent.pushed[0], StopAgentUserMessage)

    _assert_no_synthesized_settlement(local_task, services, chat_message.message_id)


def test_completed_answer_after_cursor_is_redelivered_raw(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """On the production path a cleanly-completed answer is settled by the
    derived cursor (both the chat and the answer derive as settled, and the
    cursor lands on the answer -- the latest in log order), so dedup drops it
    before the loop ever sees it. Two lower-level pins remain:

    Part (a): ``_drop_already_processed_messages`` stops walking as soon as it
    finds the cursor id, so given a cursor at the chat message it leaves the
    trailing answer LIVE in the queue rather than re-queued -- the walk never
    inspects messages behind the cursor.

    Part (b): an answer that does reach the loop via the live input queue is
    re-delivered RAW to the agent, never converted to a resume, relying on the
    harness to skip it as a stale dialog turn.
    """
    workspace_id = WorkspaceID()
    chat_message = _make_in_flight_chat_message()
    answer = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"Continue?": "Yes, proceed"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    )
    stale_state = AgentTaskStateV2(workspace_id=workspace_id)
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            answer,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id),
            RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id),
        ],
    )

    # Production path: the derived cursor settles both messages and lands on the
    # answer, so dedup would drop both from the replayed queue.
    assert _scan_history(local_task, services).last_processed_message_id == answer.message_id

    # Part (a): a cursor sitting at the chat message drops it and leaves the
    # trailing answer live in the queue -- not captured as "re-queued".
    replay_queue: Queue = Queue()
    replay_queue.put(chat_message)
    replay_queue.put(answer)
    dropped, re_queued = _drop_already_processed_messages(chat_message.message_id, replay_queue)

    assert dropped == (chat_message,)
    assert re_queued == ()
    assert replay_queue.qsize() == 1
    assert replay_queue.get() == answer

    # Part (b): running the loop with the answer live in input_message_queue (as
    # part (a) leaves it) shows what actually happens to it.
    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordingIdleStopAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    input_message_queue.put(answer)
    shutdown_event = threading.Event()
    shutdown_event.set()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                history_scan=_scan_history(local_task, services),
                re_queued_messages=(),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    delivered_for_answer = [
        m for m in fake_agent.pushed if isinstance(m, (UserQuestionAnswerMessage, ResumeAgentResponseRunnerMessage))
    ]
    assert len(delivered_for_answer) == 1, f"expected exactly one dispatch for the answer, got {delivered_for_answer}"
    assert isinstance(delivered_for_answer[0], UserQuestionAnswerMessage), (
        f"pin: a cleanly-completed answer still live in the queue is re-delivered RAW, not resumed; got {type(delivered_for_answer[0]).__name__}"
    )
