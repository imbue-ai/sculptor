import threading
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from pydantic import AnyUrl
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
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.artifacts import FileAgentArtifact
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import TaskID
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
from sculptor.tasks.handlers.run_agent.setup import _drop_already_processed_messages
from sculptor.tasks.handlers.run_agent.setup import load_initial_task_state
from sculptor.tasks.handlers.run_agent.v1 import AgentPaused
from sculptor.tasks.handlers.run_agent.v1 import _build_agent_path
from sculptor.tasks.handlers.run_agent.v1 import _run_agent_in_environment
from sculptor.tasks.handlers.run_agent.v1 import _save_messages
from sculptor.tasks.handlers.run_agent.v1 import _send_user_input_message
from sculptor.tasks.handlers.run_agent.v1 import _update_task_state


def test_drop_already_processed_messages_with_processed_id() -> None:
    """Test dropping messages up to last_processed_input_message_id."""
    user_queue: Queue[Message] = Queue()

    msg1 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    msg2 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Second message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    target_msg = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Target message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    msg3 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Should remain",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    user_queue.put(msg1)
    user_queue.put(msg2)
    user_queue.put(target_msg)
    user_queue.put(msg3)

    dropped, _ = _drop_already_processed_messages(
        last_processed_input_message_id=target_msg.message_id,
        user_message_queue=user_queue,
    )

    assert len(dropped) == 3
    assert dropped == (msg1, msg2, target_msg)
    assert user_queue.qsize() == 1
    assert user_queue.get() == msg3


def test_drop_already_processed_messages_none_values() -> None:
    """Test edge case with None value for last_processed_input_message_id."""
    user_queue: Queue[Message] = Queue()

    msg1 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="First message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    msg2 = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Second message",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )

    user_queue.put(msg1)
    user_queue.put(msg2)

    dropped, _ = _drop_already_processed_messages(
        last_processed_input_message_id=None,
        user_message_queue=user_queue,
    )

    assert len(dropped) == 0
    assert user_queue.qsize() == 2


def test_drop_already_processed_messages_empty_queue() -> None:
    """Test with empty queue."""
    user_queue: Queue[Message] = Queue()

    dropped, _ = _drop_already_processed_messages(
        last_processed_input_message_id=None,
        user_message_queue=user_queue,
    )

    assert len(dropped) == 0
    assert user_queue.empty()


def test_build_agent_path_unpackaged_strips_venv_from_front_and_appends_to_end() -> None:
    """Venv bin dir should be moved from its prepended position to the end of PATH, and sculpt-bin prepended."""
    venv_bin = Path("/home/user/sculptor/.venv/bin")
    sculpt_dir = Path("/home/user/.dev_sculptor/internal/sculpt-bin")
    current_path = "/home/user/sculptor/.venv/bin:/usr/local/bin:/usr/bin"

    result = _build_agent_path(
        is_packaged=False,
        executable_parent=venv_bin,
        current_path=current_path,
        sculpt_dir=sculpt_dir,
    )

    assert (
        result == "/home/user/.dev_sculptor/internal/sculpt-bin:/usr/local/bin:/usr/bin:/home/user/sculptor/.venv/bin"
    )


def test_build_agent_path_unpackaged_strips_all_occurrences_of_venv_bin() -> None:
    """If venv bin appears multiple times in PATH, all occurrences should be stripped."""
    venv_bin = Path("/home/user/sculptor/.venv/bin")
    sculpt_dir = Path("/home/user/.dev_sculptor/internal/sculpt-bin")
    current_path = "/home/user/sculptor/.venv/bin:/usr/local/bin:/home/user/sculptor/.venv/bin:/usr/bin"

    result = _build_agent_path(
        is_packaged=False,
        executable_parent=venv_bin,
        current_path=current_path,
        sculpt_dir=sculpt_dir,
    )

    assert (
        result == "/home/user/.dev_sculptor/internal/sculpt-bin:/usr/local/bin:/usr/bin:/home/user/sculptor/.venv/bin"
    )


def test_build_agent_path_unpackaged_with_no_venv_in_path() -> None:
    """If venv bin is not in PATH, PATH should be unchanged with venv appended and sculpt-bin prepended."""
    venv_bin = Path("/home/user/sculptor/.venv/bin")
    sculpt_dir = Path("/home/user/.dev_sculptor/internal/sculpt-bin")
    current_path = "/usr/local/bin:/usr/bin"

    result = _build_agent_path(
        is_packaged=False,
        executable_parent=venv_bin,
        current_path=current_path,
        sculpt_dir=sculpt_dir,
    )

    assert (
        result == "/home/user/.dev_sculptor/internal/sculpt-bin:/usr/local/bin:/usr/bin:/home/user/sculptor/.venv/bin"
    )


def test_build_agent_path_unpackaged_with_empty_path() -> None:
    """If PATH is empty, result should be sculpt-bin + empty + venv bin dir."""
    venv_bin = Path("/home/user/sculptor/.venv/bin")
    sculpt_dir = Path("/home/user/.dev_sculptor/internal/sculpt-bin")

    result = _build_agent_path(
        is_packaged=False,
        executable_parent=venv_bin,
        current_path="",
        sculpt_dir=sculpt_dir,
    )

    assert result == "/home/user/.dev_sculptor/internal/sculpt-bin::/home/user/sculptor/.venv/bin"


def test_build_agent_path_packaged_mode_prepends_sculpt_dir() -> None:
    """In packaged mode, sculpt dir should be prepended to PATH."""
    executable_parent = Path("/app/resources/sculptor_backend")
    sculpt_dir = Path("/app/resources/sculpt")
    current_path = "/usr/local/bin:/usr/bin"

    result = _build_agent_path(
        is_packaged=True,
        executable_parent=executable_parent,
        current_path=current_path,
        sculpt_dir=sculpt_dir,
    )

    assert result == "/app/resources/sculpt:/usr/local/bin:/usr/bin"


def _set_task_state(task: Task, state: AgentTaskStateV2, services: ServiceCollectionForTask) -> None:
    """Store current_state on a task in the database."""
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task.object_id)
        assert task_row is not None
        updated = task_row.evolve(task_row.ref().current_state, state.model_dump())
        transaction.upsert_task(updated)


def _get_task_title(task: Task, services: ServiceCollectionForTask) -> str | None:
    """Read the current title from the database."""
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task.object_id)
        assert task_row is not None
        assert task_row.current_state is not None
        return AgentTaskStateV2.model_validate(task_row.current_state).title


def test_update_task_state_overwrites_renamed_title(
    local_task: Task,
    services: ServiceCollectionForTask,
) -> None:
    """_update_task_state clobbers a title that was renamed via the API.

    Simulates the race condition:
    1. Agent loads task state with title "Original Title"
    2. User renames the agent to "Renamed Title" (updates DB)
    3. Agent processes a message and calls _update_task_state with stale state
    4. DB title is overwritten back to "Original Title"
    """
    workspace_id = WorkspaceID()
    initial_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        title="Original Title",
        last_processed_message_id=None,
    )
    _set_task_state(local_task, initial_state, services)

    # Step 1: Agent loads state into memory (capturing "Original Title").
    in_memory_state = initial_state

    # Step 2: User renames agent via API (directly updating DB).
    renamed_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        title="Renamed Title",
        last_processed_message_id=None,
    )
    _set_task_state(local_task, renamed_state, services)
    assert _get_task_title(local_task, services) == "Renamed Title"

    # Step 3: Agent finishes processing and calls _update_task_state with stale state.
    new_message_id = AgentMessageID()
    _update_task_state(
        last_processed_input_message_id=new_message_id,
        task_id=local_task.object_id,
        task_state=in_memory_state,
        services=services,
    )

    # Step 4: The renamed title should be preserved, not overwritten.
    assert _get_task_title(local_task, services) == "Renamed Title"


class _SigtermOnFirstPushAgent(DefaultAgentWrapper):
    """Fake agent that mimics what happens to the wrapper when Claude is SIGTERM'd mid-turn.

    On the first ``ChatInputUserMessage`` pushed in, it queues the same RequestStarted /
    RequestStopped pair that ``DefaultAgentWrapper._handle_user_message`` produces when an
    ``AgentClientError(exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)`` escapes, and sets
    ``_exit_code = SIGTERM`` so the next ``poll()`` returns the kill exit code.
    """

    def _start(self) -> None: ...

    def _terminate(self, force_kill_seconds: float) -> None: ...

    def wait(self, timeout: float) -> int:
        return self._exit_code if self._exit_code is not None else 0

    def _push_message(self, message: Message) -> bool:
        if not isinstance(message, ChatInputUserMessage):
            return False
        self._output_messages.put(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=message.message_id,
            )
        )
        try:
            raise AgentClientError("Killed by SIGTERM", exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)
        except AgentClientError as exc:
            sigterm_error = SerializedException.build(exc, exc.__traceback__)
        self._output_messages.put(
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=message.message_id,
                error=sigterm_error,
            )
        )
        self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
        return True


def test_sigtermed_in_flight_message_is_recorded_as_processed(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """When the agent is SIGTERM'd mid-turn, the in-flight user message must be recorded
    as ``last_processed_message_id`` so the next agent run does not re-deliver it to Claude.

    Reproduces the user-visible bug: on the next run, ``_drop_already_processed_messages``
    keys off ``last_processed_message_id`` to decide which queued messages to drop. If the
    interrupted message wasn't recorded as processed, it survives in the queue and the
    main loop pushes it to Claude again — making the agent appear to auto-start with the
    user's previously-interrupted prompt.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    in_flight_message = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Long-running prompt",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Persist the chat message — in production it would have been written via
    # the HTTP send endpoint before the agent picked it up via subscription.
    # _record_latest_completion_in_state needs the user message in the DB to
    # distinguish it from ephemeral request_ids (e.g. StopAgentUserMessage's).
    with services.data_model_service.open_task_transaction() as transaction:
        services.task_service.create_message(in_flight_message, local_task.object_id, transaction)

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _SigtermOnFirstPushAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(in_flight_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(local_task.object_id)
        assert task_row is not None
        final_state = AgentTaskStateV2.model_validate(task_row.current_state)
        assert final_state.last_processed_message_id == in_flight_message.message_id


class _AukThenSigtermOnStopAgent(DefaultAgentWrapper):
    """Fake agent that mimics the AUQ-pending shutdown sequence.

    On the first ``ChatInputUserMessage``: emits ``RequestStartedAgentMessage`` and an
    ``AskUserQuestionAgentMessage`` (ephemeral) so the v1 loop sees the AUQ and
    sets ``is_waiting_for_question_answer = True``. The loop then clears
    ``user_input_message_being_processed = None`` at v1.py:600.

    To trigger the shutdown leg cleanly without orchestrating the
    ``shutdown_event`` from outside the loop, the agent fires the supplied event
    from inside ``pop_messages`` after the AUQ message has been delivered to the
    loop. The next loop iteration sees the event, pushes ``StopAgentUserMessage``,
    and the fake responds by emitting ``RequestStoppedAgentMessage`` for the
    original chat message (matching what ``DefaultAgentWrapper._handle_user_message``
    does on an ``AgentClientError(SIGTERM)``) and setting ``_exit_code = SIGTERM``
    so the following iteration takes the poll-based early-exit path into
    ``_handle_completed_agent``.
    """

    _shutdown_event_to_trigger: threading.Event | None = PrivateAttr(default=None)
    _chat_message_id: AgentMessageID | None = PrivateAttr(default=None)
    _auq_emitted: bool = PrivateAttr(default=False)

    def arm_shutdown(self, event: threading.Event) -> None:
        self._shutdown_event_to_trigger = event

    def _start(self) -> None: ...

    def _terminate(self, force_kill_seconds: float) -> None: ...

    def wait(self, timeout: float) -> int:
        return self._exit_code if self._exit_code is not None else 0

    def pop_messages(self) -> list[MessageTypes]:
        messages = super().pop_messages()
        event = self._shutdown_event_to_trigger
        if self._auq_emitted and event is not None and not event.is_set():
            event.set()
        return messages

    def _push_message(self, message: Message) -> bool:
        if isinstance(message, ChatInputUserMessage):
            self._chat_message_id = message.message_id
            self._output_messages.put(
                RequestStartedAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=message.message_id,
                )
            )
            self._output_messages.put(
                AskUserQuestionAgentMessage(
                    message_id=AgentMessageID(),
                    question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
                )
            )
            self._auq_emitted = True
            return True
        if isinstance(message, StopAgentUserMessage):
            chat_message_id = self._chat_message_id
            assert chat_message_id is not None, "Stop arrived before any chat message"
            try:
                raise AgentClientError("Killed by SIGTERM", exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)
            except AgentClientError as exc:
                err = SerializedException.build(exc, exc.__traceback__)
            self._output_messages.put(
                RequestStoppedAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=chat_message_id,
                    error=err,
                )
            )
            self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
            return True
        return False


def test_sigtermed_during_auq_wait_records_chat_message_as_processed(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """When the agent is SIGTERM'd while waiting for an AskUserQuestion answer,
    the in-flight chat message must still be recorded as ``last_processed_message_id``.

    In the AUQ-pending state the v1 loop sets ``user_input_message_being_processed = None``
    (v1.py:600) by design — the original chat message is still in flight as far as
    Claude is concerned, but the local variable doesn't reflect that. A fix that
    keys off ``user_input_message_being_processed`` (hypothesis #1's fix) won't
    update state in this scenario, leaving the chat prompt ahead of the dedup
    cursor and re-delivered to Claude on the next agent run.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Make a plan and ask me to approve it",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Persist the chat message — in production it would have been written via
    # the HTTP send endpoint before the agent picked it up.
    with services.data_model_service.open_task_transaction() as transaction:
        services.task_service.create_message(chat_message, local_task.object_id, transaction)

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _AukThenSigtermOnStopAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    fake_agent.arm_shutdown(shutdown_event)

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(local_task.object_id)
        assert task_row is not None
        final_state = AgentTaskStateV2.model_validate(task_row.current_state)
        assert final_state.last_processed_message_id == chat_message.message_id


def test_load_initial_task_state_derives_last_processed_from_history(
    local_task: Task,
    services: ServiceCollectionForTask,
) -> None:
    """If the DB shows a completion for a user message that isn't reflected in
    task_state.last_processed_message_id, load_initial_task_state should derive
    the corrected value from history.

    Reproduces hypothesis #3: the v1 loop's success path commits _save_messages
    (v1.py:510) and _update_task_state (v1.py:557-562) in separate transactions.
    If the backend is SIGKILL'd or loses power between them, the completion
    message is persisted but last_processed_message_id is stale. Without
    reconciliation, the next agent run leaves the user message ahead of the
    dedup cursor and re-delivers it to Claude.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message_id = AgentMessageID()
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Persist a user chat message + its completion to the DB. This is the state
    # left behind by a crash between _save_messages and _update_task_state in
    # the v1 loop's success path.
    chat_message = ChatInputUserMessage(
        message_id=chat_message_id,
        text="Processed but not recorded",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    with services.data_model_service.open_task_transaction() as transaction:
        services.task_service.create_message(chat_message, local_task.object_id, transaction)
        services.task_service.create_message(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message_id,
            ),
            local_task.object_id,
            transaction,
        )
        services.task_service.create_message(
            RequestSuccessAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message_id,
            ),
            local_task.object_id,
            transaction,
        )

    loaded_state, _project = load_initial_task_state(services, local_task)

    assert loaded_state.last_processed_message_id == chat_message_id

    # The correction must also be persisted so downstream dedup
    # (wait_for_initial_message_and_process_queue -> _drop_already_processed_messages)
    # sees the corrected value when it re-reads task_state from the DB.
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(local_task.object_id)
        assert task_row is not None
        persisted_state = AgentTaskStateV2.model_validate(task_row.current_state)
        assert persisted_state.last_processed_message_id == chat_message_id


class _RecordOnlyAgent(DefaultAgentWrapper):
    """Fake agent that records pushed chat/resume messages without doing real work.

    On ``StopAgentUserMessage`` (which the v1 loop pushes when it observes
    ``shutdown_event``), the agent emits ``RequestStoppedAgentMessage`` for the most
    recent chat message and sets ``_exit_code = SIGTERM`` so the next loop iteration
    early-returns into ``_handle_completed_agent`` via the poll() check.
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
            try:
                raise AgentClientError("Killed by SIGTERM", exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)
            except AgentClientError as exc:
                err = SerializedException.build(exc, exc.__traceback__)
            self._output_messages.put(
                RequestStoppedAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=chat_id,
                    error=err,
                )
            )
            self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
            return True
        return False


def test_in_flight_message_with_partial_response_is_sent_as_resume_not_chat(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """If the persisted history shows a chat message that the agent started processing,
    emitted a partial response for, but never completed (e.g. Sculptor backend SIGKILL
    or power loss mid-response), the loop must send a ``ResumeAgentResponseRunnerMessage``
    on the next run so Claude continues its existing ``--resume`` session rather than
    restarting the prompt from scratch.

    Reproduces hypothesis #2: ``v1.py:445`` unconditionally sets
    ``initial_in_flight_user_chat_message_id = None`` (FIXME from commit
    ``bc3922e4e2c4``, "Disable the new message resumption behavior"), throwing away
    the value the history walk just computed. ``_send_user_input_message`` then
    sees the loop's effective in-flight ID as ``None``, fails the equality check
    at v1.py:681, and pushes the chat message as-is instead of converting to a
    resume.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Long prompt",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Persist the in-flight state: the chat message, its RequestStartedAgentMessage,
    # and a partial agent response (ResponseBlockAgentMessage). No completion message
    # was ever emitted — this is what a SIGKILL mid-response leaves behind.
    with services.data_model_service.open_task_transaction() as transaction:
        services.task_service.create_message(chat_message, local_task.object_id, transaction)
        services.task_service.create_message(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
            ),
            local_task.object_id,
            transaction,
        )
        services.task_service.create_message(
            ResponseBlockAgentMessage(
                message_id=AgentMessageID(),
                role="assistant",
                assistant_message_id=AssistantMessageID(generate_id()),
                content=(TextBlock(text="I'll start by..."),),
            ),
            local_task.object_id,
            transaction,
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
    shutdown_event.set()  # Fire immediately so the loop sends Stop on its first iteration.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert fake_agent.pushed_chat_or_resume, "Expected the loop to push at least one chat/resume message"
    first_push = fake_agent.pushed_chat_or_resume[0]
    assert isinstance(first_push, ResumeAgentResponseRunnerMessage), (
        f"Expected first push to be ResumeAgentResponseRunnerMessage, got {type(first_push).__name__}"
    )
    assert first_push.for_user_message_id == chat_message.message_id


def test_resuming_in_flight_message_does_not_persist_a_duplicate(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """Resuming an in-flight chat message must not re-persist it.

    When Sculptor is hard-killed mid-response (``RequestStarted`` persisted, no
    completion), the message is re-queued on restart and sent as a
    ``ResumeAgentResponseRunnerMessage``. The message was already saved when it
    was first sent (that's why it has a ``RequestStarted`` and is being
    resumed), so ``_send_user_input_message`` must NOT save it again. A second
    ``saved_agent_message`` row with the same ``object_id`` makes the replay
    project that id into both ``completed_chat_messages`` and
    ``queued_chat_messages`` -- so it renders as a sent message AND a stuck
    queued message that never clears. This is the write-side root cause of the
    duplicate-render bug.

    Drives the full ``_run_agent_in_environment`` resume path and asserts the
    on-disk row count for the in-flight message stays at exactly one.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Long prompt",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Persist the in-flight state exactly once: the chat message, its
    # RequestStartedAgentMessage, and a partial agent response. No completion
    # message was ever emitted -- this is what a SIGKILL mid-response leaves.
    with services.data_model_service.open_task_transaction() as transaction:
        services.task_service.create_message(chat_message, local_task.object_id, transaction)
        services.task_service.create_message(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
            ),
            local_task.object_id,
            transaction,
        )
        services.task_service.create_message(
            ResponseBlockAgentMessage(
                message_id=AgentMessageID(),
                role="assistant",
                assistant_message_id=AssistantMessageID(generate_id()),
                content=(TextBlock(text="I'll start by..."),),
            ),
            local_task.object_id,
            transaction,
        )

    # Precondition: exactly one copy on disk before we resume. If this fails,
    # the setup -- not the fix under test -- is wrong.
    with services.data_model_service.open_task_transaction() as transaction:
        rows_before = services.task_service.get_saved_messages_for_task(local_task.object_id, transaction)
    chat_rows_before = [message for message in rows_before if message.message_id == chat_message.message_id]
    assert len(chat_rows_before) == 1, (
        f"test precondition: in-flight message should be persisted exactly once, got {len(chat_rows_before)}"
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
    shutdown_event.set()  # Fire immediately so the loop sends Stop after the first send.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(chat_message,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    # Sanity: it really did take the resume path.
    assert fake_agent.pushed_chat_or_resume, "Expected the loop to push at least one chat/resume message"
    assert isinstance(fake_agent.pushed_chat_or_resume[0], ResumeAgentResponseRunnerMessage)

    # The in-flight message must appear exactly once in the persisted log -- the
    # resume must not write a duplicate row with the same object_id.
    with services.data_model_service.open_task_transaction() as transaction:
        saved_messages = services.task_service.get_saved_messages_for_task(local_task.object_id, transaction)
    chat_copies = [message for message in saved_messages if message.message_id == chat_message.message_id]
    assert len(chat_copies) == 1, (
        f"resumed in-flight message must not be re-persisted; found {len(chat_copies)} copies in saved_agent_message"
    )


class _RecordAnswerOrResumeAgent(DefaultAgentWrapper):
    """Fake agent that records whether the loop dispatched a raw answer or a resume.

    Mirrors ``_RecordOnlyAgent`` but for the crash-mid-answer restore path: it
    records pushed ``UserQuestionAnswerMessage`` and
    ``ResumeAgentResponseRunnerMessage`` so a test can assert which one the loop
    sent for an orphaned answer. On the ``StopAgentUserMessage`` the v1 loop pushes
    when it observes ``shutdown_event``, it emits a ``RequestStoppedAgentMessage``
    for the most recent dispatched request and sets ``_exit_code =
    AGENT_EXIT_CODE_FROM_SIGTERM`` so the next iteration early-exits into
    ``_handle_completed_agent``.
    """

    _pushed_answer_or_resume: list[UserQuestionAnswerMessage | ResumeAgentResponseRunnerMessage] = PrivateAttr(
        default_factory=list
    )
    _last_request_id: AgentMessageID | None = PrivateAttr(default=None)

    def _start(self) -> None: ...

    def _terminate(self, force_kill_seconds: float) -> None: ...

    def wait(self, timeout: float) -> int:
        return self._exit_code if self._exit_code is not None else 0

    @property
    def pushed_answer_or_resume(self) -> list[UserQuestionAnswerMessage | ResumeAgentResponseRunnerMessage]:
        return self._pushed_answer_or_resume

    def _push_message(self, message: Message) -> bool:
        if isinstance(message, UserQuestionAnswerMessage):
            self._pushed_answer_or_resume.append(message)
            self._last_request_id = message.message_id
            return True
        if isinstance(message, ResumeAgentResponseRunnerMessage):
            self._pushed_answer_or_resume.append(message)
            self._last_request_id = message.for_user_message_id
            return True
        if isinstance(message, StopAgentUserMessage):
            request_id = self._last_request_id
            assert request_id is not None, "Stop arrived before any answer/resume message"
            try:
                raise AgentClientError("Killed by SIGTERM", exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)
            except AgentClientError as exc:
                err = SerializedException.build(exc, exc.__traceback__)
            self._output_messages.put(
                RequestStoppedAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=request_id,
                    error=err,
                )
            )
            self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
            return True
        return False


def test_orphaned_question_answer_is_resumed_not_stale_skipped(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """SCU-1558: a question answer whose turn died mid-flight must be RESUMED on
    restart, not re-delivered raw.

    A crash mid-question-answer leaves the ``UserQuestionAnswerMessage`` with a
    ``RequestStarted`` but no completion -- the per-turn ``RequestSuccess`` is
    deferred to the turn boundary, which the crash never reaches. Reconciliation
    keeps the orphaned answer in the queue, so the resume loop re-dispatches it.

    On restart the pi process has already recorded the answer as a ``toolResult``
    and has no open dialog, so re-delivering the answer raw is reported as a stale
    dialog and dropped (``_deliver_question_answer`` emits ``RequestSkipped``): no
    turn is driven and the request never settles, leaving a perpetually-busy agent.

    The loop must instead convert the orphaned answer to a
    ``ResumeAgentResponseRunnerMessage`` -- the same contract it already honors for
    an orphaned chat message -- so the dangling request settles.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = _make_in_flight_chat_message()
    answer = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"Which option?": "the first one"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Persist the crash-mid-answer history: the chat turn started and produced a
    # partial response, then the user's answer was delivered (RequestStarted) but
    # its turn never completed -- no completion message for either request.
    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            answer,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordAnswerOrResumeAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()  # Fire immediately so the loop sends Stop after the first send.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(answer,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert fake_agent.pushed_answer_or_resume, "Expected the loop to dispatch the orphaned answer"
    first_push = fake_agent.pushed_answer_or_resume[0]
    assert isinstance(first_push, ResumeAgentResponseRunnerMessage), (
        f"orphaned answer must be resumed, not re-delivered raw (which is stale-skipped); got {type(first_push).__name__}"
    )
    assert first_push.for_user_message_id == answer.message_id


def test_send_user_input_message_resumes_only_the_orphaned_answer() -> None:
    """Only the answer tracked as orphaned converts to a resume; any other is raw.

    Guards the boundary of the SCU-1558 fix: a live answer (one not left in flight
    by a previous, crashed run) must still reach the harness as a raw
    UserQuestionAnswerMessage so it is delivered to the open dialog. Converting it
    to a resume would silently drop the user's actual answer.
    """
    orphaned = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"q": "a"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    )
    live = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"q": "b"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t2"),
        tool_use_id="t2",
    )

    orphaned_agent = MagicMock()
    _send_user_input_message(
        orphaned_agent,
        orphaned,
        None,
        orphaned.message_id,
    )
    (orphaned_call,) = orphaned_agent.push_message.call_args_list
    sent_for_orphaned = orphaned_call.args[0]
    assert isinstance(sent_for_orphaned, ResumeAgentResponseRunnerMessage)
    assert sent_for_orphaned.for_user_message_id == orphaned.message_id

    live_agent = MagicMock()
    _send_user_input_message(
        live_agent,
        live,
        None,
        orphaned.message_id,
    )
    (live_call,) = live_agent.push_message.call_args_list
    assert live_call.args[0] is live, "a live answer must be delivered raw, not converted to a resume"


def test_orphaned_answer_with_interrupted_completion_is_still_resumed(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """An answer whose only completion is interrupted stays orphaned and resumes.

    A post-answer shutdown can leave the answer with RequestStarted +
    RequestSuccess(interrupted=True): the deferred per-turn success fired during
    teardown, but the follow-up turn was never driven. That is not a finished turn,
    so the resume replay must keep treating the answer as orphaned and convert it
    to a ResumeAgentResponseRunnerMessage. Clearing it on the interrupted
    completion would fall back to raw re-delivery, which a fresh agent stale-skips
    — re-introducing the bug on the next restart.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = _make_in_flight_chat_message()
    answer = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"q": "a"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # Crash-mid-answer history where the answer's deferred success fired interrupted
    # during teardown: RequestStarted + RequestSuccess(interrupted=True), no clean
    # completion and no follow-up turn.
    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            answer,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id),
            RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id, interrupted=True),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordAnswerOrResumeAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()  # Fire immediately so the loop sends Stop after the first send.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(answer,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert fake_agent.pushed_answer_or_resume, "Expected the loop to dispatch the orphaned answer"
    first_push = fake_agent.pushed_answer_or_resume[0]
    assert isinstance(first_push, ResumeAgentResponseRunnerMessage), (
        f"interrupted answer completion must keep the orphan resumable; got {type(first_push).__name__}"
    )
    assert first_push.for_user_message_id == answer.message_id


def test_answer_with_clean_completion_is_not_resumed(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A cleanly-completed answer is cleared from orphan tracking, not resumed.

    A clean (non-interrupted) RequestSuccess means the answer's turn actually
    finished, so the replay must clear it. If such an answer still reaches the
    resume loop it is delivered raw (its dialog round is genuinely over), never
    converted to a resume — the negative side of the clearing condition.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = _make_in_flight_chat_message()
    answer = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"q": "a"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # The answer's turn finished cleanly: RequestStarted + RequestSuccess(interrupted=False).
    _persist_messages(
        local_task,
        services,
        [
            chat_message,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=chat_message.message_id),
            _make_partial_response_block(),
            answer,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id),
            RequestSuccessAgentMessage(message_id=AgentMessageID(), request_id=answer.message_id, interrupted=False),
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _RecordAnswerOrResumeAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()
    shutdown_event.set()  # Fire immediately so the loop sends Stop after the first send.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(answer,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert fake_agent.pushed_answer_or_resume, "Expected the loop to dispatch the answer"
    first_push = fake_agent.pushed_answer_or_resume[0]
    assert isinstance(first_push, UserQuestionAnswerMessage), (
        f"a cleanly-completed answer must not be resumed; got {type(first_push).__name__}"
    )


class _CompletingResumeAgent(DefaultAgentWrapper):
    """Fake agent that COMPLETES resumed turns, keyed on ``for_user_message_id``.

    Where ``_RecordOnlyAgent`` only records pushes, this agent emits the
    RequestStarted / RequestSuccess pair the real wrapper emits for a resumed
    turn (request_id = the resumed turn's ``for_user_message_id``), driving
    the loop's ``is_agent_turn_finished`` and
    dedup-cursor paths so tests can assert what happens AFTER a resumed turn
    finishes.

    Ends the run (via a SIGTERM exit code, like ``_RecordOnlyAgent``) when the
    loop dispatches a plain chat message.
    """

    _pushed: list[ChatInputUserMessage | ResumeAgentResponseRunnerMessage] = PrivateAttr(default_factory=list)

    def _start(self) -> None: ...

    def _terminate(self, force_kill_seconds: float) -> None: ...

    def wait(self, timeout: float) -> int:
        return self._exit_code if self._exit_code is not None else 0

    @property
    def pushed(self) -> list[ChatInputUserMessage | ResumeAgentResponseRunnerMessage]:
        return self._pushed

    def _push_message(self, message: Message) -> bool:
        if isinstance(message, ResumeAgentResponseRunnerMessage):
            self._pushed.append(message)
            self._output_messages.put(
                RequestStartedAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=message.for_user_message_id,
                )
            )
            self._output_messages.put(
                RequestSuccessAgentMessage(
                    message_id=AgentMessageID(),
                    request_id=message.for_user_message_id,
                )
            )
            return True
        if isinstance(message, ChatInputUserMessage):
            self._pushed.append(message)
            self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
            return True
        return False


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


def _read_persisted_task_state(local_task: Task, services: ServiceCollectionForTask) -> AgentTaskStateV2:
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(local_task.object_id)
        assert task_row is not None
        return AgentTaskStateV2.model_validate(task_row.current_state)


def test_queued_followup_is_dispatched_after_resumed_turn_completes(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """The headline stuck-queued-message scenario, end-to-end at the loop level.

    Hard kill mid-turn with message A in flight (RequestStarted + partial
    response, no completion) and follow-up B queued behind it. On restart the
    loop must resume A, and -- because the resumed turn's completion is keyed on
    ``for_user_message_id`` -- ``is_agent_turn_finished`` must fire when it
    completes so that B is dispatched. The dedup cursor must advance to A so A
    is not re-delivered on the run after this one.

    This binds the two halves of the contract that the wrapper-level test
    (``agent_wrapper_test.test_resume_turn_uses_for_user_message_id_as_request_id``)
    and this module's resume tests pin separately: the wrapper emits completions
    keyed on the original turn id, and the loop acts on them.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    message_a = _make_in_flight_chat_message()
    message_b = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Queued follow-up",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    # What a SIGKILL mid-turn leaves on disk: A saved + started + partial
    # response; B saved (queued, never started); no completions.
    _persist_messages(
        local_task,
        services,
        [
            message_a,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=message_a.message_id),
            _make_partial_response_block(),
            message_b,
        ],
    )

    agent_env = LocalAgentExecutionEnvironment(
        environment=environment,
        task_id=local_task.object_id,
        dependency_management_service=services.dependency_management_service,
    )
    fake_agent = _CompletingResumeAgent(
        harness=CLAUDE_CODE_HARNESS,
        environment=agent_env,
        task_id=local_task.object_id,
        system_prompt="",
    )

    input_message_queue: Queue = Queue()
    shutdown_event = threading.Event()  # NOT set: the run ends when B is dispatched.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(message_a, message_b),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    # A went out as a resume, and after its completion the queued follow-up B
    # was dispatched as a plain chat message.
    assert len(fake_agent.pushed) == 2, f"expected [resume(A), B], got {fake_agent.pushed}"
    first, second = fake_agent.pushed
    assert isinstance(first, ResumeAgentResponseRunnerMessage)
    assert first.for_user_message_id == message_a.message_id
    assert isinstance(second, ChatInputUserMessage)
    assert second.message_id == message_b.message_id

    # The dedup cursor advanced to A, so A is not re-delivered on the next run.
    persisted_state = _read_persisted_task_state(local_task, services)
    assert persisted_state.last_processed_message_id == message_a.message_id, (
        f"cursor must advance to A on resumed-turn completion; got {persisted_state.last_processed_message_id}"
    )


def test_double_hard_kill_without_resumed_turn_output_resends_fresh(
    local_task: Task,
    services: ServiceCollectionForTask,
    project: Project,
    environment: LocalEnvironment,
    test_settings: SculptorSettings,
) -> None:
    """A second hard kill BEFORE the resumed turn produced output -> fresh re-send.

    The history walk resets ``is_partial_agent_response`` on each
    RequestStarted for the chat message (v1.py), so a resumed turn that died
    without emitting any ResponseBlock leaves "nothing to continue from" and the
    next run pushes the original prompt as a fresh ChatInputUserMessage instead
    of a resume. This pins that semantic choice -- and that the fresh re-send
    path does not re-persist the message either.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    message_a = _make_in_flight_chat_message()
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    _persist_messages(
        local_task,
        services,
        [
            message_a,
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=message_a.message_id),
            _make_partial_response_block(),
            # -- first hard kill + restart: the resumed turn starts (same request_id)
            # and is killed again before emitting any output.
            RequestStartedAgentMessage(message_id=AgentMessageID(), request_id=message_a.message_id),
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
    shutdown_event.set()  # Fire immediately so the loop sends Stop after the first send.

    assert isinstance(local_task.input_data, AgentTaskInputsV2)
    task_data = local_task.input_data

    with patch("sculptor.tasks.handlers.run_agent.v1._get_agent_wrapper", return_value=fake_agent):
        with pytest.raises(AgentPaused):
            _run_agent_in_environment(
                task=local_task,
                task_data=task_data,
                task_state=stale_state,
                re_queued_messages=(message_a,),
                input_message_queue=input_message_queue,
                environment=agent_env,
                services=services,
                project=project,
                settings=test_settings,
                shutdown_event=shutdown_event,
            )

    assert fake_agent.pushed_chat_or_resume, "Expected the loop to push at least one chat/resume message"
    first_push = fake_agent.pushed_chat_or_resume[0]
    assert isinstance(first_push, ChatInputUserMessage), (
        f"Expected a fresh re-send when the resumed turn produced no output, got {type(first_push).__name__}"
    )
    assert first_push.message_id == message_a.message_id

    with services.data_model_service.open_task_transaction() as transaction:
        saved_messages = services.task_service.get_saved_messages_for_task(local_task.object_id, transaction)
    chat_copies = [message for message in saved_messages if message.message_id == message_a.message_id]
    assert len(chat_copies) == 1, f"fresh re-send must not re-persist; found {len(chat_copies)} copies"


def test_load_initial_task_state_does_not_count_interrupted_completions(
    local_task: Task,
    services: ServiceCollectionForTask,
) -> None:
    """Reconciliation must not treat interrupted completions as truly processed.

    Reproduces hypothesis #12 (post-answer shutdown): when the user answered an
    AUQ and Sculptor was killed before Claude finished processing the answer, the
    wrapper emits ``RequestSuccessAgentMessage(answer, interrupted=True)`` and
    ``RequestStoppedAgentMessage(X)``. Both are
    ``PersistentRequestCompleteAgentMessage``s — but neither represents a
    fully-processed message: the chat X was SIGTERM'd mid-response, and the
    answer was SIGTERM'd mid-MCP-delivery.

    If reconciliation counts these as "processed", it sets
    ``last_processed_message_id = answer.message_id`` and dedup drops the answer
    from the queue on the next run. The user's typed answer is silently lost.

    With the fix, reconciliation skips completions flagged as ``interrupted`` or
    detected as killed (SIGTERM/SIGINT). For the post-answer-shutdown scenario,
    neither X nor answer is counted, so ``last_processed_message_id`` stays at
    its prior value and the answer survives in the queue to be re-delivered.
    """
    workspace_id = WorkspaceID()
    previous_message_id = AgentMessageID()
    chat_message = ChatInputUserMessage(
        message_id=AgentMessageID(),
        text="Pick an option",
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    answer = UserQuestionAnswerMessage(
        message_id=AgentMessageID(),
        answers={"q": "a"},
        question_data=AskUserQuestionData(questions=[], tool_use_id="t1"),
        tool_use_id="t1",
    )
    stale_state = AgentTaskStateV2(
        workspace_id=workspace_id,
        last_processed_message_id=previous_message_id,
    )
    _set_task_state(local_task, stale_state, services)

    try:
        raise AgentClientError("Killed by SIGTERM", exit_code=AGENT_EXIT_CODE_FROM_SIGTERM)
    except AgentClientError as exc:
        sigterm_error = SerializedException.build(exc, exc.__traceback__)

    with services.data_model_service.open_task_transaction() as transaction:
        services.task_service.create_message(chat_message, local_task.object_id, transaction)
        services.task_service.create_message(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
            ),
            local_task.object_id,
            transaction,
        )
        services.task_service.create_message(answer, local_task.object_id, transaction)
        services.task_service.create_message(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=answer.message_id,
            ),
            local_task.object_id,
            transaction,
        )
        # Answer's RequestSuccess with interrupted=True (post-CLI finally block on SIGTERM).
        services.task_service.create_message(
            RequestSuccessAgentMessage(
                message_id=AgentMessageID(),
                request_id=answer.message_id,
                interrupted=True,
            ),
            local_task.object_id,
            transaction,
        )
        # Chat message's RequestStopped (wrapper's except handler on SIGTERM).
        services.task_service.create_message(
            RequestStoppedAgentMessage(
                message_id=AgentMessageID(),
                request_id=chat_message.message_id,
                error=sigterm_error,
            ),
            local_task.object_id,
            transaction,
        )

    loaded_state, _project = load_initial_task_state(services, local_task)

    # Today: reconciliation counts both completions and sets last_processed
    # to answer.message_id (the latest). The answer would then be dropped by dedup.
    # After fix: neither counts (both are interrupted/killed), so last_processed
    # stays at previous_message_id and the answer survives for re-delivery.
    assert loaded_state.last_processed_message_id != answer.message_id, (
        "Reconciliation must not advance last_processed past the answer's interrupted completion"
    )
    assert loaded_state.last_processed_message_id == previous_message_id


def test_save_messages_writes_artifact_before_publishing_its_message() -> None:
    """SCU-1295: each artifact's sync callback must run before the publish
    callback of its corresponding ``UpdatedArtifactAgentMessage``.

    The on-disk task-sync file backs the HTTP ``/artifacts/{name}`` endpoint.
    If the publish fires first, the frontend's ``useArtifactSync`` fetches the
    file before ``set_artifact_file_data`` has run, hits a 404, silently
    swallows the failure, and clears its update marker — the StatusPill
    popover empties out until a *later* agent action triggers another fetch
    that wins the race.

    Surgical contract (decided in Phase 1): non-artifact messages still
    publish *before* the artifact sync, so chat tokens don't pay the
    file-write latency of an artifact update sharing their batch.
    """
    registered: list[str] = []

    class LabeledCallback:
        def __init__(self, label: str) -> None:
            self.label = label

        def __call__(self) -> None:
            return None

    class RecordingTransaction:
        def add_callback(self, callback: object) -> None:
            registered.append(callback.label if isinstance(callback, LabeledCallback) else "unknown")

    transaction = RecordingTransaction()

    @contextmanager
    def fake_open_transaction():
        yield transaction

    def fake_create_message(message: object, _task_id: TaskID, txn: RecordingTransaction) -> None:
        txn.add_callback(LabeledCallback(f"publish:{type(message).__name__}"))

    services = MagicMock()
    services.data_model_service.open_task_transaction = fake_open_transaction
    services.task_service.create_message = fake_create_message

    chat_msg = ResponseBlockAgentMessage(
        role="assistant",
        message_id=AgentMessageID(),
        assistant_message_id=AssistantMessageID(generate_id()),
        content=(TextBlock(text="hello"),),
    )
    artifact_msg = UpdatedArtifactAgentMessage(
        message_id=AgentMessageID(),
        artifact=FileAgentArtifact(
            name=ArtifactType.PLAN.value,
            url=AnyUrl("file:///tmp/PLAN-test.json"),
        ),
    )

    _save_messages(
        TaskID(),
        services,
        [chat_msg, artifact_msg],
        {ArtifactType.PLAN.value: LabeledCallback("sync:PLAN")},
    )

    chat_publish_idx = registered.index("publish:ResponseBlockAgentMessage")
    artifact_publish_idx = registered.index("publish:UpdatedArtifactAgentMessage")
    sync_idx = registered.index("sync:PLAN")

    assert sync_idx < artifact_publish_idx, (
        f"sync:PLAN must run before publish:UpdatedArtifactAgentMessage so the file is on disk by the time the frontend fetches it; got {registered}"
    )
    assert chat_publish_idx < sync_idx, (
        f"non-artifact publishes should run before any artifact sync (surgical interleave — chat tokens shouldn't wait for artifact writes); got {registered}"
    )
