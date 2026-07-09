import datetime
import os
import sys
import time
from pathlib import Path
from queue import Empty
from queue import Queue
from typing import Any
from typing import Callable
from typing import Sequence
from typing import TypeVar
from typing import assert_never
from typing import cast

from loguru import logger

from sculptor.agents.harness_registry import create_agent_for_run
from sculptor.agents.harness_registry import get_harness_for_config
from sculptor.agents.pi_agent.agent_wrapper import PiAgent
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import NotificationImportance
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.common import is_live_debugging
from sculptor.foundation.concurrency_group import ConcurrencyExceptionGroup
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.concurrency_group import ConcurrentShutdownError
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.errors import ExpectedError
from sculptor.foundation.event_utils import CancelledByEventError
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.nested_evolver import assign
from sculptor.foundation.nested_evolver import chill
from sculptor.foundation.nested_evolver import evolver
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import Agent
from sculptor.interfaces.agents.agent import AgentCrashedRunnerMessage
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentCrashedRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentReleasedRunnerMessage
from sculptor.interfaces.agents.agent import EnvironmentTypes
from sculptor.interfaces.agents.agent import KilledAgentRunnerMessage
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import ModelsAvailableAgentMessage
from sculptor.interfaces.agents.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.agent import PersistentRunnerMessageUnion
from sculptor.interfaces.agents.agent import PersistentUserMessageUnion
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UnexpectedErrorRunnerMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.artifacts import FileAgentArtifact
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
from sculptor.interfaces.agents.constants import SIGINT_EXIT_CODES
from sculptor.interfaces.agents.constants import SIGTERM_EXIT_CODES
from sculptor.interfaces.agents.errors import AgentCrashed
from sculptor.interfaces.agents.errors import UncleanTerminationAgentError
from sculptor.interfaces.agents.errors import WaitTimeoutAgentError
from sculptor.interfaces.agents.harness import AgentRunContext
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.interfaces.environments.errors import EnvironmentFailure
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.task_service.api import TaskService
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import TaskError
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.services.task_service.errors import UserStoppedTaskError
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
from sculptor.state.messages import ModelOption
from sculptor.state.messages import PersistentAgentMessage
from sculptor.state.messages import PersistentUserMessage
from sculptor.tasks.handlers.run_agent.setup import HistoryScan
from sculptor.tasks.handlers.run_agent.setup import finalize_task_setup
from sculptor.tasks.handlers.run_agent.setup import get_killed_exit_code
from sculptor.tasks.handlers.run_agent.setup import load_initial_task_state
from sculptor.tasks.handlers.run_agent.setup import message_queue_subscription_context
from sculptor.tasks.handlers.run_agent.setup import scan_message_history
from sculptor.tasks.handlers.run_agent.setup import title_prediction_context
from sculptor.tasks.handlers.run_agent.setup import wait_for_initial_message_and_process_queue
from sculptor.utils.build import build_sculpt_backend_env
from sculptor.utils.build import get_sculpt_bin_dir
from sculptor.utils.build import is_packaged
from sculptor.utils.shutdown import GLOBAL_SHUTDOWN_EVENT
from sculptor.utils.timeout import TIMING_LOG_THRESHOLD_SECONDS
from sculptor.utils.timeout import format_timing_log
from sculptor.utils.timeout import log_runtime

# it will take at most this much time to notice when the process has finished
_POLL_SECONDS: float = 1.0
# how long to wait for the agent to shut down after the user has requested it (before killing it)
_MAX_SOFT_SHUTDOWN_SECONDS: float = 10.0
# how long to wait when hard killing the agent after the soft shutdown has been requested
_MAX_HARD_SHUTDOWN_SECONDS: float = 10.0
# how long to wait for an already-completed agent to fully finish (and surface any exception)
_COMPLETED_AGENT_FINAL_WAIT_SECONDS: float = 10.0


class AgentTaskFailure(TaskError):
    pass


class AgentHardKilled(ExpectedError):
    pass


class AgentShutdownCleanly(ExpectedError):
    pass


class AgentPaused(AgentShutdownCleanly):
    """
    The agent was paused by the user (typically via ctrl-c) and will be resumed when the process restarts.
    """


def run_agent_task_v1(
    task_data: AgentTaskInputsV2,
    task: Task,
    services: ServiceCollectionForTask,
    task_deadline: datetime.datetime | None,
    settings: SculptorSettings,
    concurrency_group: ConcurrencyGroup,
    shutdown_event: ReadOnlyEvent,
    on_agent_started: Callable[[], None] | None = None,
) -> Callable[[DataModelTransaction], Any] | None:
    """
    At a high level, the purpose of this task is to run an Agent in an Environment.

    Messages from the user are handled as "requests" to the agent, which may be made in parallel.

    Because of this, agents should emit `PersistentRequestCompleteAgentMessage`s  when they have finished processing a message.
    This enables us to snapshot the state of the agent when all messages have been processed.

    Note that this means there is no guarantee that the agent will be able to snapshot --
    if there are continually many pending messages, the state is never guaranteed to be consistent,
    and thus we will not snapshot it.

    Like all tasks, this task should be idempotent, so it can be restarted at any time.

    This task creates the image if it doesn't exist, then creates an `Environment` and runs the `Agent` inside.
    Really, the purpose is just to get everything to a place where we can call `_run_agent_in_environment`

    `run_agent_task_v1` is responsible for the setup and error handling --
    see `_run_agent_in_environment` for the core event loop of the Agent.
    """
    user_reference = task.user_reference
    task_id = task.object_id

    root_progress_handle = RootProgressHandle()

    try:
        logger.debug("running task {} for user {}", task_id, user_reference)
        setup_start_time = time.monotonic()

        # Load task state and project
        task_state, project = load_initial_task_state(services, task)

        # Replay the persisted message log once to derive the loop's startup state:
        # the in-flight (resumable) messages and the dedup cursor. Fetching this
        # early is safe because no agent runs between this fetch and the loop start
        # in _run_agent_in_environment, so no RequestStarted or completion messages
        # can be persisted in the gap; user messages that arrive during the initial
        # wait below cannot be in flight and reach the loop via the live
        # input_message_queue.
        with services.data_model_service.open_task_transaction() as transaction:
            all_messages = services.task_service.get_saved_messages_for_task(task.object_id, transaction)
        history_scan = scan_message_history(all_messages, get_harness_for_config(task_data.agent_config))

        # Subscribe to the message queue, set up the environment, then wait for the initial message.
        # Environment setup happens before the initial message wait so that prompt-less agents
        # (created via the "Add agent" button) reach READY state while waiting for user input.
        with (
            message_queue_subscription_context(task, services) as input_message_queue,
            concurrency_group.make_concurrency_group(name=f"run_agent_v1_{task_id}") as environment_concurrency_group,
        ):
            # Set up environment
            with services.workspace_service.agent_environment_context(
                project=project,
                workspace_id=task_state.workspace_id,
                task_id=task.object_id,
                concurrency_group=environment_concurrency_group,
                root_progress_handle=root_progress_handle,
                shutdown_event=shutdown_event,
            ) as environment:
                # Emit EnvironmentAcquiredRunnerMessage
                # Access the underlying LocalEnvironment for the message
                assert isinstance(environment, LocalAgentExecutionEnvironment)
                underlying_env = cast(EnvironmentTypes, environment.underlying_environment)
                with services.data_model_service.open_task_transaction() as transaction:
                    services.task_service.create_message(
                        EnvironmentAcquiredRunnerMessage(environment=underlying_env),
                        task_id=task.object_id,
                        transaction=transaction,
                    )
                try:
                    # Signal the frontend that a diff is available without generating
                    # it now. The actual artifact is created on-demand when the
                    # frontend fetches GET /workspaces/{id}/diff.  This avoids
                    # running expensive git diff commands during agent startup.
                    services.workspace_service.mark_workspace_diff_stale(
                        task_state.workspace_id,
                    )

                    # For a pi agent, fetch + persist pi's model catalog now (a
                    # short-lived probe) so the switcher shows pi's own models
                    # while the agent waits prompt-less below — start() (and its
                    # catalog fetch) is deferred to the first message. Gated to pi
                    # and best-effort, so it neither starts non-pi agents eagerly
                    # nor fails the run if the probe cannot reach pi.
                    try:
                        task_state = _eager_fetch_pi_models_into_state(
                            task=task,
                            task_data=task_data,
                            task_state=task_state,
                            environment=environment,
                            project=project,
                            settings=settings,
                            services=services,
                            in_testing=settings.TESTING.INTEGRATION_ENABLED,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.info("Pi model pre-fetch failed ({}); switcher will fall back to defaults", e)

                    # Now wait for the initial user message (may block for prompt-less agents)
                    re_queued_messages, initial_message = wait_for_initial_message_and_process_queue(
                        input_message_queue, history_scan.last_processed_message_id, shutdown_event
                    )

                    # A pre-first-message model switch is written to task state out of band
                    # from this in-memory copy; re-read so the selection is not lost here.
                    task_state = _refresh_model_fields_from_db(task.object_id, task_state, services)

                    with title_prediction_context(
                        task_state,
                        initial_message,
                        settings,
                        environment_concurrency_group,
                        root_progress_handle,
                    ) as (
                        title_result,
                        title_thread,
                    ):
                        # Handle git initialization and branch setup
                        task_state = finalize_task_setup(
                            task=task,
                            task_state=task_state,
                            title_thread=title_thread,
                            title_result=title_result,
                            initial_message=initial_message,
                            services=services,
                        )
                    setup_duration = time.monotonic() - setup_start_time
                    if setup_duration >= TIMING_LOG_THRESHOLD_SECONDS:
                        logger.debug(format_timing_log("task setup", setup_duration))

                    logger.debug("time after restart: {}", time.monotonic())
                    # and run the agent in the environment until it either finishes or the environment dies
                    return _run_agent_in_environment(
                        task=task,
                        task_data=task_data,
                        task_state=task_state,
                        history_scan=history_scan,
                        re_queued_messages=re_queued_messages,
                        input_message_queue=input_message_queue,
                        environment=environment,
                        services=services,
                        project=project,
                        settings=settings,
                        shutdown_event=shutdown_event,
                        on_agent_started=on_agent_started,
                    )
                finally:
                    # Emit EnvironmentReleasedRunnerMessage
                    with services.data_model_service.open_task_transaction() as transaction:
                        services.task_service.create_message(
                            EnvironmentReleasedRunnerMessage(),
                            task_id=task.object_id,
                            transaction=transaction,
                        )
    # handle ConcurrencyExceptionGroup as a general exception
    except ConcurrencyExceptionGroup as e:
        on_exception(e, task_id, user_reference, services, shutdown_event)
    # all other exceptions should be handled and turned into task failures
    except Exception as e:
        on_exception(e, task_id, user_reference, services, shutdown_event)
    return None


def _build_agent_path(*, is_packaged: bool, executable_parent: Path, current_path: str, sculpt_dir: Path) -> str:
    """Build the PATH environment variable for agent subprocesses.

    ``sculpt_dir`` (a directory containing only the ``sculpt`` CLI) is prepended
    so that ``sculpt`` always resolves to our build, regardless of how user
    shell init reorders PATH.

    When running from source (not packaged), the server runs inside a uv-managed
    venv (via ``uv run``) that has editable installs of workspace members
    (sculptor, sculptor.foundation, etc.) pointing at the server's source tree. If agents
    inherit the venv's bin dir at the front of PATH, they use the venv Python —
    which imports from the server's source tree instead of the workspace clone's,
    causing cross-workspace pollution. So in dev mode we additionally strip the
    venv bin dir from its prepended position and re-append it at the end.
    """
    sculpt_dir_str = str(sculpt_dir)
    if not is_packaged:
        venv_bin = str(executable_parent)
        clean_path = os.pathsep.join(p for p in current_path.split(os.pathsep) if p != venv_bin)
        return f"{sculpt_dir_str}{os.pathsep}{clean_path}{os.pathsep}{venv_bin}"
    return f"{sculpt_dir_str}{os.pathsep}{current_path}"


def _run_agent_in_environment(
    task: Task,
    task_data: AgentTaskInputsV2,
    task_state: AgentTaskStateV2,
    history_scan: HistoryScan,
    re_queued_messages: tuple[PersistentUserMessageUnion, ...],
    input_message_queue: Queue[UserMessageUnion | ResumeAgentResponseRunnerMessage],
    environment: AgentExecutionEnvironment,
    services: ServiceCollectionForTask,
    project: Project,
    settings: SculptorSettings,
    shutdown_event: ReadOnlyEvent,
    on_agent_started: Callable[[], None] | None = None,
) -> Callable[[DataModelTransaction], Any] | None:
    """
    The core agent event loop: runs the Agent in the given Environment.

    Think of this sort of like a "main" loop in a game engine:
    - it starts the agent, and then continuously polls for new messages from the agent and the user
    - it handles the agent's output (eg, by sending it to the database)
    - it handles the user messages (eg, by sending them to the agent)
    - it syncs artifacts from the agent's output to the task_service

    ``history_scan`` is the replay of the task's persisted message log (see
    ``scan_message_history``), which seeds the loop's view of what a previous run
    left in flight.
    """
    # state: these variables are changed as the agent runs
    shutdown_started_at: float | None = None
    # we process the user input messages one at a time
    # there are other messages from the user besides PersistentUserMessage, but the other ones are control flow
    # and have nothing to do with snapshotting
    user_input_message_being_processed: PersistentUserMessage | None = None
    queued_user_input_messages: list[PersistentUserMessageUnion] = list(re_queued_messages)
    last_user_chat_message_id: AgentMessageID | None = history_scan.last_user_chat_message_id
    # track the full history of persistent messages we've seen
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage] = list(
        history_scan.persistent_message_history
    )
    initial_in_flight_user_chat_message_id = history_scan.in_flight_chat_message_id
    initial_in_flight_user_question_answer_message_id = history_scan.in_flight_answer_message_id
    # tool_use_ids of questions the agent asked that haven't been answered yet;
    # while non-empty, queued messages must not be dequeued — only answers should
    # be sent. A set (not a flag) because multiple questions can pend at once:
    # subagents can each ask mid-turn, and answering one must not make the
    # runner forget it is still waiting on the others.
    pending_question_tool_use_ids: set[str] = set()
    with log_runtime("run_agent_in_environment pre-processing"):
        # figure out what command we need to run (eg, which agent to invoke)
        in_testing = settings.TESTING.INTEGRATION_ENABLED

        def on_diff_needed() -> None:
            services.workspace_service.maybe_refresh_workspace_diff(task_state.workspace_id)

        agent_wrapper = _get_agent_wrapper(
            task_data=task_data,
            task_state=task_state,
            environment=environment,
            project=project,
            task_id=task.object_id,
            workspace_service=services.workspace_service,
            in_testing=in_testing,
            on_diff_needed=on_diff_needed,
        )
        secrets = _build_agent_secrets(settings=settings, task=task, task_state=task_state, project=project)
        agent_wrapper.start(secrets)
        if on_agent_started is not None:
            on_agent_started()

        # The last chat turn the agent started processing carries the
        # conversation's launch settings (model, fast mode, effort); model-less
        # turns (question answers) continue with them, so they are re-seeded
        # into the agent wrapper from the replayed history.
        if history_scan.last_started_chat_message is not None:
            agent_wrapper.set_conversation_launch_settings(
                model_name=history_scan.last_started_chat_message.model_name,
                fast_mode=history_scan.last_started_chat_message.fast_mode,
                effort=history_scan.last_started_chat_message.effort,
            )

        logger.debug("Initial in-flight user chat message ID: {}", initial_in_flight_user_chat_message_id)
        logger.debug("Derived last processed message id:      {}", history_scan.last_processed_message_id)

        # When a crash left orphaned requests (RequestStarted with no terminal
        # completion) and no pending user input will drive their resume,
        # synthesize an interrupted completion so the frontend settles to READY
        # instead of staying stuck "thinking" forever.
        #
        # The chat candidate is the scan's DANGLING id (no accepted terminal
        # completion), not the post-partial-gate in-flight id: a crash before any
        # output leaves a dangling request with nothing to resume from, and it must
        # still be terminalized here — settling it as an empty interrupted turn
        # rather than silently re-executing a possibly-side-effectful prompt.
        pending_input_message_ids = {message.message_id for message in queued_user_input_messages} | {
            message.message_id for message in input_message_queue.queue
        }
        orphan_request_ids = [
            rid
            for rid in (
                history_scan.dangling_chat_message_id,
                initial_in_flight_user_question_answer_message_id,
            )
            if rid is not None and rid not in pending_input_message_ids
        ]
        orphaned_completion_msgs = [
            RequestSuccessAgentMessage(
                message_id=AgentMessageID(),
                request_id=rid,
                interrupted=True,
                turn_abandoned=True,
            )
            for rid in orphan_request_ids
        ]
        if orphaned_completion_msgs:
            _save_messages(task.object_id, services, orphaned_completion_msgs, {})
            # No cursor write is needed: the next run's scan_message_history sees
            # the turn_abandoned completion and derives the message as settled.

    # this is the core event loop for the agent.
    exit_code: int | None

    # if we start with an existing queue, send the first message
    if len(queued_user_input_messages) > 0:
        user_input_message_being_processed = _send_user_input_message(
            agent_wrapper,
            queued_user_input_messages.pop(0),
            initial_in_flight_user_chat_message_id,
            initial_in_flight_user_question_answer_message_id,
        )
    while True:
        # if we have been trying to shut down for too long, it is time for more drastic measures.
        if shutdown_started_at is not None and time.monotonic() - shutdown_started_at > _MAX_SOFT_SHUTDOWN_SECONDS:
            # go see where it is hung if we can
            kill_time_start = time.monotonic()
            try:
                agent_wrapper.terminate(_MAX_HARD_SHUTDOWN_SECONDS)
                remaining_shutdown_time = _MAX_HARD_SHUTDOWN_SECONDS - (time.monotonic() - kill_time_start)
                if remaining_shutdown_time <= 0:
                    raise UncleanTerminationAgentError("No time left to call wait() on agent wrapper")
                exit_code = agent_wrapper.wait(remaining_shutdown_time)
            except (UncleanTerminationAgentError, WaitTimeoutAgentError) as e:
                raise AgentHardKilled(
                    f"Agent took longer than {_MAX_SOFT_SHUTDOWN_SECONDS + _MAX_HARD_SHUTDOWN_SECONDS} seconds to shut down"
                ) from e
            else:
                return _handle_completed_agent(
                    agent_wrapper,
                    exit_code,
                    task,
                    project,
                    environment,
                    services,
                )

        # if the process has completed
        exit_code = agent_wrapper.poll()
        if exit_code is not None:
            return _handle_completed_agent(
                agent_wrapper,
                exit_code,
                task,
                project,
                environment,
                services,
            )

        # transfer any output from the process
        new_messages = agent_wrapper.pop_messages()
        callbacks = sync_artifacts(
            new_messages, task, project, environment, services.git_repo_service, services.task_service
        )

        # save the new messages off
        _save_messages(task.object_id, services, new_messages, callbacks)

        # detect if the agent asked a question during this batch of messages
        for message in new_messages:
            if isinstance(message, AskUserQuestionAgentMessage):
                pending_question_tool_use_ids.add(message.question_data.tool_use_id)
            elif pending_question_tool_use_ids and isinstance(
                message, (RequestFailureAgentMessage, RequestStoppedAgentMessage)
            ):
                # SCU-530: the agent's chat request failed or was stopped while we
                # were still waiting for an answer to an AUQ — the CLI consumer of
                # that answer is gone, so stop waiting. Without this, subsequent
                # ChatInputUserMessages match the guard at line 624 and get silently
                # appended to ``queued_user_input_messages`` forever.
                pending_question_tool_use_ids.clear()

        # add any persistent messages to our history
        for message in new_messages:
            if isinstance(message, PersistentAgentMessage):
                killed_exit_code = get_killed_exit_code(message)
                if killed_exit_code:
                    logger.debug("Agent seems like it exited, returning")
                    return _handle_completed_agent(
                        agent_wrapper,
                        killed_exit_code,
                        task,
                        project,
                        environment,
                        services,
                    )
                else:
                    persistent_message_history.append(message)

        # Persist any model catalog the agent surfaced this batch (pi emits one at
        # start) onto task state so the harness's get_available_models reads it.
        task_state = _record_available_models_in_state(new_messages, task.object_id, task_state, services)

        # Did the currently-pending in-flight message complete? Drives the dispatch
        # decision below.
        is_agent_turn_finished = user_input_message_being_processed is not None and any(
            isinstance(m, PersistentRequestCompleteAgentMessage)
            and m.request_id == user_input_message_being_processed.message_id
            for m in new_messages
        )
        if (
            is_agent_turn_finished
            and user_input_message_being_processed is not None
            and isinstance(user_input_message_being_processed, ChatInputUserMessage)
        ):
            last_user_chat_message_id = user_input_message_being_processed.message_id

        # send the next message (if there is one waiting). Under the SDK MCP
        # AUQ flow the original chat-input request stays "in flight" while
        # the agent is blocked on the user's answer (the CLI doesn't exit on
        # AUQ anymore), so ``is_agent_turn_finished`` never fires for the
        # AUQ-triggering message — gate this block on either condition so
        # the answer can be dispatched mid-turn.
        if is_agent_turn_finished or pending_question_tool_use_ids:
            if pending_question_tool_use_ids:
                # The agent asked a question — don't dequeue the next message yet.
                # Wait for the UserQuestionAnswerMessage before continuing.
                # However, the answer may have already arrived and been queued while the
                # previous processing thread was still winding down. Check for it now.
                queued_answer = None
                remaining: list[PersistentUserMessageUnion] = []
                for queued_msg in queued_user_input_messages:
                    if queued_answer is None and isinstance(queued_msg, UserQuestionAnswerMessage):
                        queued_answer = queued_msg
                    else:
                        remaining.append(queued_msg)
                queued_user_input_messages = remaining
                if queued_answer is not None:
                    pending_question_tool_use_ids.discard(queued_answer.tool_use_id)
                    user_input_message_being_processed = _send_user_input_message(
                        agent_wrapper,
                        queued_answer,
                        initial_in_flight_user_chat_message_id,
                        initial_in_flight_user_question_answer_message_id,
                    )
                else:
                    user_input_message_being_processed = None
            elif len(queued_user_input_messages) == 0:
                user_input_message_being_processed = None
            else:
                user_input_message_being_processed = _send_user_input_message(
                    agent_wrapper,
                    queued_user_input_messages.pop(0),
                    initial_in_flight_user_chat_message_id,
                    initial_in_flight_user_question_answer_message_id,
                )

        # get any new user message(s)
        user_messages = _get_input_messages(input_message_queue, max_wait_time=_POLL_SECONDS)

        # If the program is shutting down, simply stop the thread.
        if environment.concurrency_group.is_shutting_down():
            # At the moment, stopping implies pausing.
            raise AgentPaused()

        # if we observed a shutdown event, send a stop message to the agent and start the timer
        if shutdown_started_at is None and shutdown_event.is_set():
            logger.debug("Shutdown event observed, sending stop message to agent.")
            agent_wrapper.push_message(StopAgentUserMessage())
            shutdown_started_at = time.monotonic()

        # send the user messages to the process
        for message in user_messages:
            # handle input chat user messages one at a time
            if isinstance(message, PersistentUserMessage):
                if isinstance(message, ChatInputUserMessage) and last_user_chat_message_id is None:
                    last_user_chat_message_id = message.message_id
                if pending_question_tool_use_ids and not isinstance(message, UserQuestionAnswerMessage):
                    # While the agent is waiting for a question answer, queue all other
                    # messages — only the answer should be sent to the agent.
                    queued_user_input_messages.append(message)
                elif user_input_message_being_processed is None:
                    if isinstance(message, UserQuestionAnswerMessage):
                        pending_question_tool_use_ids.discard(message.tool_use_id)
                    user_input_message_being_processed = _send_user_input_message(
                        agent_wrapper,
                        message,
                        initial_in_flight_user_chat_message_id,
                        initial_in_flight_user_question_answer_message_id,
                    )
                else:
                    queued_user_input_messages.append(message)
                # add it to the conversation history
                persistent_message_history.append(message)
            # otherwise, simply forward the message to the agent and let it figure it out
            else:
                agent_wrapper.push_message(message)


InputMessageT = TypeVar("InputMessageT", bound=UserMessageUnion | ResumeAgentResponseRunnerMessage)


def _send_user_input_message(
    agent_wrapper: Agent,
    message: InputMessageT,
    initial_in_flight_user_chat_message_id: AgentMessageID | None,
    initial_in_flight_user_question_answer_message_id: AgentMessageID | None,
) -> InputMessageT:
    user_input_message_being_processed = message
    # if this message was one that we left off on last time,
    # we need to send a special "Please pick up where you left off" message instead of the normal message
    # this allows the agent to use whatever in-flight response it had
    # (which prevents the user from losing a bunch of work if they shut down or sculptor crashed)
    # this is especially important as agents start to have much longer response times
    #
    # Do NOT re-persist a resumed message here. We only convert a message that is
    # being resumed after a restart, which means it already has a RequestStarted in
    # the log and was therefore already saved when it was first sent. Calling
    # create_message again would write a second saved_agent_message row with the
    # same object_id; replay then projects that id into both completed_chat_messages
    # and queued_chat_messages, so it renders as a sent message AND a stuck queued
    # message that never clears (and the duplicate React key corrupts the
    # virtualized list).
    if user_input_message_being_processed.message_id == initial_in_flight_user_chat_message_id and isinstance(
        user_input_message_being_processed, ChatInputUserMessage
    ):
        resume_message = ResumeAgentResponseRunnerMessage(
            for_user_message_id=user_input_message_being_processed.message_id,
            model_name=user_input_message_being_processed.model_name,
            fast_mode=user_input_message_being_processed.fast_mode,
            effort=user_input_message_being_processed.effort,
        )
        agent_wrapper.push_message(resume_message)
    elif (
        user_input_message_being_processed.message_id == initial_in_flight_user_question_answer_message_id
        and isinstance(user_input_message_being_processed, UserQuestionAnswerMessage)
    ):
        # Resume the orphaned answer (tracked during replay) instead of re-delivering
        # it raw, which a fresh agent with no open dialog stale-skips.
        # UserQuestionAnswerMessage carries no model/effort, so the resume defaults
        # those: it continues the turn, it does not start a fresh prompt.
        resume_message = ResumeAgentResponseRunnerMessage(
            for_user_message_id=user_input_message_being_processed.message_id,
        )
        agent_wrapper.push_message(resume_message)
    else:
        agent_wrapper.push_message(user_input_message_being_processed)
    return user_input_message_being_processed


def on_exception(
    e: Exception,
    task_id: TaskID,
    user_reference: UserReference,
    services: ServiceCollectionForTask,
    shutdown_event: ReadOnlyEvent,
) -> None:
    # During graceful shutdown, any ConcurrencyExceptionGroup is shutdown-related (whether it
    # contains one or many exceptions).  Check this BEFORE unwrapping single-exception groups,
    # because the unwrapped exception might not be a recognized shutdown type.
    if isinstance(e, ConcurrencyExceptionGroup) and (shutdown_event.is_set() or GLOBAL_SHUTDOWN_EVENT.is_set()):
        raise UserPausedTaskError() from e

    # For simple exceptions that bubble up wrapped in a ConcurrencyExceptionGroup, unwrap them.
    if isinstance(e, ConcurrencyExceptionGroup) and len(e.exceptions) == 1:
        e = e.exceptions[0]

    # ConcurrentShutdownError is raised when the ConcurrencyGroup is torn down during server
    # shutdown.  Treat it the same as AgentPaused so the task is re-queued, not failed.
    if isinstance(e, ConcurrentShutdownError):
        raise UserPausedTaskError() from e

    # this "exception" is expected in the sense that it was the user telling the task to stop
    # so it doesn't count as success
    if isinstance(e, CancelledByEventError) and (shutdown_event.is_set() or GLOBAL_SHUTDOWN_EVENT.is_set()):
        # Looks like the user cancelled the task even before the agent started.
        raise UserPausedTaskError() from e
    if isinstance(e, (AgentPaused, UserPausedTaskError)):
        raise UserPausedTaskError() from e
    if isinstance(e, AgentShutdownCleanly):
        raise UserStoppedTaskError() from e

    # if the agent has failed, we should notify the user
    is_expected = isinstance(e, ExpectedError)
    if is_expected:
        log_exception(
            exc=e,
            message="Agent runner failed with expected error",
            priority=ExceptionPriority.LOW_PRIORITY,
        )
    else:
        if is_live_debugging():
            raise
        log_exception(
            exc=e,
            message="Agent runner failed with unexpected error",
            priority=ExceptionPriority.MEDIUM_PRIORITY,
        )

    error = e

    # send a message to the user
    is_worth_notifying = True
    agent_error_message: PersistentRunnerMessageUnion
    match error:
        case AgentHardKilled():
            agent_error_message = KilledAgentRunnerMessage(message_id=AgentMessageID())
            # not worth notifying the user about this, they told it to stop
            is_worth_notifying = False
        case AgentCrashed():
            agent_error_message = AgentCrashedRunnerMessage(
                message_id=AgentMessageID(),
                exit_code=error.exit_code,
                error=SerializedException.build(error),
            )
        case EnvironmentFailure():
            agent_error_message = EnvironmentCrashedRunnerMessage(
                message_id=AgentMessageID(),
                error=SerializedException.build(error),
            )
        case _:
            agent_error_message = UnexpectedErrorRunnerMessage(
                message_id=AgentMessageID(),
                error=SerializedException.build(error),
            )

    def on_transaction(t: DataModelTransaction) -> None:
        services.task_service.create_message(agent_error_message, task_id, t)

        # and send a notification to the user if necessary
        if is_worth_notifying:
            task_row = services.task_service.get_task(task_id, t)
            assert task_row is not None
            t.insert_notification(
                Notification(
                    user_reference=user_reference,
                    object_id=NotificationID(),
                    message="Agent failed.",
                    importance=NotificationImportance.TIME_SENSITIVE,
                    task_id=task_row.object_id,
                ),
            )

    # During shutdown, any unrecognized exception should be treated as a pause rather than a failure.
    # This catches cases where exceptions from cleanup code (e.g., DB writes in finally blocks)
    # mask the original shutdown exception.
    if shutdown_event.is_set() or GLOBAL_SHUTDOWN_EVENT.is_set():
        raise UserPausedTaskError() from e

    # raising will ensure that unexpected Exceptions are logged, and that the task is marked as failed
    raise AgentTaskFailure(transaction_callback=on_transaction, is_user_notified=True)


def _build_agent_secrets(
    settings: SculptorSettings,
    task: Task,
    task_state: AgentTaskStateV2,
    project: Project,
) -> dict[str, str]:
    """Build the backend-env + PATH secrets an agent subprocess launches with.

    Shared by `_run_agent_in_environment` (the normal `agent_wrapper.start`) and
    the pre-message pi catalog probe (`_eager_fetch_pi_models_into_state`), which
    spawns a throwaway pi process with the same environment.
    """
    secrets: dict[str, str] = build_sculpt_backend_env(
        backend_port=settings.BACKEND_PORT,
        workspace_id=task_state.workspace_id,
        project_id=project.object_id,
        agent_id=task.object_id,
    )
    executable_parent = Path(sys.executable).parent
    secrets["PATH"] = _build_agent_path(
        is_packaged=is_packaged(),
        executable_parent=executable_parent,
        current_path=os.environ.get("PATH", ""),
        sculpt_dir=get_sculpt_bin_dir(executable_parent),
    )
    return secrets


def _eager_fetch_pi_models_into_state(
    task: Task,
    task_data: AgentTaskInputsV2,
    task_state: AgentTaskStateV2,
    environment: AgentExecutionEnvironment,
    project: Project,
    settings: SculptorSettings,
    services: ServiceCollectionForTask,
    in_testing: bool,
) -> AgentTaskStateV2:
    """Populate the switcher's model catalog for a fresh pi agent, before the first message.

    `run_agent_task_v1` keeps a prompt-less agent READY without calling
    `agent_wrapper.start()` until a message arrives, so pi's start-time
    `_fetch_models_into_state` has not run and the task's catalog is still
    `NOT_FETCHED_YET` — the switcher shows a loading state, not the empty state.
    Here, once the environment is ready, we run a short-lived pi probe
    (`PiAgent.fetch_available_models_probe`) and persist its curated catalog onto
    task state so the switcher reflects pi's models immediately.

    Returns the task state evolved with the probe's result, so the caller carries
    it forward — otherwise `finalize_task_setup`'s later evolve-and-upsert (from
    the in-memory state) would write the stale `NOT_FETCHED_YET` back out.
    Restricted to pi: the `supports_model_selection` check skips harnesses that
    cannot select a model at all, and the `PiAgent` check below skips the rest —
    only pi sources a dynamic catalog via the probe (Claude supports model
    selection but with a static built-in list). Best-effort: on any failure the
    probe returns an empty catalog, which is persisted as a fetched-but-empty `[]`
    (the switcher then shows the empty state) rather than left not-fetched.
    """
    if not get_harness_for_config(task_data.agent_config).capabilities().supports_model_selection:
        return task_state
    agent_wrapper = _get_agent_wrapper(
        task_data=task_data,
        task_state=task_state,
        environment=environment,
        project=project,
        task_id=task.object_id,
        workspace_service=services.workspace_service,
        in_testing=in_testing,
    )
    # Only pi sources a dynamic catalog via this probe (a PiAgent method); Claude
    # supports model selection but with a static built-in list, so it is not probed
    # here. If another harness ever sources a dynamic catalog, give it the same
    # probe seam rather than starting it eagerly here.
    if not isinstance(agent_wrapper, PiAgent):
        return task_state
    secrets = _build_agent_secrets(settings=settings, task=task, task_state=task_state, project=project)
    available_models, current_model = agent_wrapper.fetch_available_models_probe(secrets)
    # Persist even the empty result: it records that the probe COMPLETED, moving the
    # catalog off NOT_FETCHED_YET to a fetched-but-empty [] (authenticated with no
    # providers — or a best-effort probe failure, which today falls back the same
    # way). Returning early here would strand the switcher on "loading" forever.
    return _persist_available_models(
        available_models=available_models,
        current_model=current_model,
        task_id=task.object_id,
        task_state=task_state,
        services=services,
    )


def _get_agent_wrapper(
    task_data: AgentTaskInputsV2,
    task_state: AgentTaskStateV2,
    environment: AgentExecutionEnvironment,
    project: Project,
    task_id: TaskID,
    workspace_service: WorkspaceService,
    in_testing: bool = False,
    on_diff_needed: Callable[[], None] | None = None,
) -> Agent:
    logger.debug("Discriminating agent wrapper")
    context = AgentRunContext(
        task_data=task_data,
        task_state=task_state,
        environment=environment,
        project=project,
        task_id=task_id,
        workspace_service=workspace_service,
        in_testing=in_testing,
        on_diff_needed=on_diff_needed,
    )
    return create_agent_for_run(context)


def _handle_completed_agent(
    agent_wrapper: Agent,
    exit_code: int,
    task: Task,
    project: Project,
    environment: AgentExecutionEnvironment,
    services: ServiceCollectionForTask,
) -> Callable[[DataModelTransaction], None]:
    """
    Call this once the agent has finished with an exit code.

    Raises the appropriate errors and returns a callback to handle the success case.
    """

    # get any final messages
    new_messages = agent_wrapper.pop_messages()

    # and sync any necessary artifacts
    callbacks = sync_artifacts(
        new_messages, task, project, environment, services.git_repo_service, services.task_service
    )

    _save_messages(task.object_id, services, new_messages, callbacks)

    agent_wrapper.wait(
        _COMPLETED_AGENT_FINAL_WAIT_SECONDS
    )  # NOTE: if the agent has hit an exception, we will raise it here

    # if we expected to shut down, and we observed the correct exit code, fine
    if exit_code == AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT or exit_code in (
        SIGTERM_EXIT_CODES | SIGINT_EXIT_CODES
    ):
        raise AgentPaused()
    # if the process was successful, return
    elif exit_code == 0:
        return _on_success(task.object_id, task.user_reference, services.task_service)

    # if the process failed
    else:
        raise AgentCrashed(f"Agent died with exit code {exit_code}", exit_code=exit_code)


def _on_success(
    task_id: TaskID,
    user_reference: UserReference,
    task_service: TaskService,
) -> Callable[[DataModelTransaction], None]:
    """Return a finalization callback that posts the "agent finished" notification.

    Artifact syncs from this batch already fired during ``_save_messages``'s
    inner transaction (alongside the publish callbacks), so we do not
    re-register them here.
    """
    logger.debug("process finished successfully")

    def on_transaction(t: DataModelTransaction) -> None:
        task_row = task_service.get_task(task_id, t)
        assert task_row is not None
        t.insert_notification(
            Notification(
                user_reference=user_reference,
                object_id=NotificationID(),
                message="Finished running agent.",
                importance=NotificationImportance.ACTIVE,
                task_id=task_row.object_id,
            )
        )

    return on_transaction


def sync_artifacts(
    new_messages: Sequence[Message],
    task: Task,
    project: Project,
    environment: AgentExecutionEnvironment,
    git_repo_service: GitRepoService,
    task_service: TaskService,
) -> dict[str, Callable[[], Any]]:
    """Read each ``UpdatedArtifactAgentMessage``'s file contents and return a
    post-commit callback that writes them to the task's sync directory.

    Returns a map from artifact name to its sync callback. Keyed by name so
    ``_save_messages`` can pair each callback with the publish callback of its
    corresponding ``UpdatedArtifactAgentMessage`` — the sync must run first or
    the frontend's fetch can race a 404 against the file write (SCU-1295).

    Per artifact name, only the most recent occurrence's contents are kept;
    earlier emissions in the same batch are superseded by the latest one and
    their callbacks are dropped (the wire-level publishes still fire — the
    frontend coalesces duplicate fetches anyway).
    """
    # it is important that we pull the messages first --
    # this way we can guarantee that the other artifacts have been written
    # (as long as the agent wrapper does the reverse, not writing the messages until everything else is flushed)
    artifacts_to_sync = [x.artifact for x in new_messages if isinstance(x, UpdatedArtifactAgentMessage)]
    callbacks_by_name: dict[str, Callable[[], Any]] = {}
    for artifact in reversed(artifacts_to_sync):
        if artifact.name in callbacks_by_name:
            logger.trace("skipping artifact {} as it has already been synced", artifact.name)
            continue
        match artifact:
            case FileAgentArtifact():
                if artifact.url is None:
                    logger.debug("skipping artifact {} as it has no url", artifact.name)
                    continue
                logger.debug("syncing artifact: {}", artifact.url)
                remote_path = str(artifact.url).replace("file://", "")
                if not environment.exists(remote_path):
                    err = Exception(f"Artifact {artifact.name} does not exist at {remote_path}")
                    log_exception(err, "Artifact does not exist", priority=ExceptionPriority.MEDIUM_PRIORITY)
                    if is_live_debugging():
                        raise err
                    continue
                contents = environment.read_file(remote_path)
                callbacks_by_name[artifact.name] = lambda name=artifact.name, data=contents: (
                    task_service.set_artifact_file_data(task.object_id, name, data)
                )
                logger.debug("synced file artifact: {}", remote_path)
            case _ as unreachable:
                assert_never(unreachable)

    return callbacks_by_name


def _record_available_models_in_state(
    new_messages: Sequence[Message],
    task_id: TaskID,
    task_state: AgentTaskStateV2,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Persist the latest model catalog the agent surfaced this batch onto task state.

    A harness with a dynamic catalog (pi) emits a `ModelsAvailableAgentMessage`
    at agent start; this writes its `available_models` / `current_model` onto
    `AgentTaskStateV2` (which the harness's `get_available_models` /
    `get_selected_model_id` read). The last message in the batch wins. No-op when
    the batch carries none. Preserves the DB title, so a concurrent rename is not
    clobbered.
    """
    latest: ModelsAvailableAgentMessage | None = None
    for message in new_messages:
        if isinstance(message, ModelsAvailableAgentMessage):
            latest = message
    if latest is None:
        return task_state

    return _persist_available_models(
        available_models=list(latest.available_models),
        current_model=latest.current_model,
        task_id=task_id,
        task_state=task_state,
        services=services,
    )


def _refresh_model_fields_from_db(
    task_id: TaskID,
    task_state: AgentTaskStateV2,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Pull the switcher's model fields (`available_models` / `current_model`) from the DB.

    The set_model endpoint writes the selected model straight to task state while the
    agent waits for its first message, so this handler's in-memory copy goes stale.
    Refresh only those two fields (leaving the rest of the in-memory state as-is) so a
    pre-message switch reaches agent construction and survives `finalize_task_setup`'s
    write-back. A no-op when nothing changed or the task row is missing.
    """
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task_id)
    if task_row is None:
        return task_state
    db_state = AgentTaskStateV2.model_validate(task_row.current_state)
    if db_state.available_models == task_state.available_models and db_state.current_model == task_state.current_model:
        return task_state
    mutable_task_state = evolver(task_state)
    assign(mutable_task_state.available_models, lambda: db_state.available_models)
    assign(mutable_task_state.current_model, lambda: db_state.current_model)
    return chill(mutable_task_state)


def _persist_available_models(
    available_models: list[ModelOption],
    current_model: ModelOption | None,
    task_id: TaskID,
    task_state: AgentTaskStateV2,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Write a model catalog onto `AgentTaskStateV2.available_models` / `current_model`.

    Shared by the post-message path (`_record_available_models_in_state`, which
    unwraps the agent's `ModelsAvailableAgentMessage`) and the pre-message
    env-ready pi probe (`_eager_fetch_pi_models_into_state`). Routes through
    `task_service.update_available_models` so the change publishes a task update
    (a live switcher refreshes even with no message in flight, which the
    pre-message path has) and the DB title is preserved against a concurrent
    rename. Returns the evolved task state on a real change, else the input
    unchanged.
    """
    with services.data_model_service.open_task_transaction() as transaction:
        updated_task = services.task_service.update_available_models(
            task_id=task_id,
            available_models=available_models,
            current_model=current_model,
            transaction=transaction,
        )
    if updated_task is None or not isinstance(updated_task.current_state, AgentTaskStateV2):
        return task_state
    return updated_task.current_state


def _save_messages(
    task_id: TaskID,
    services: ServiceCollectionForTask,
    new_messages: Sequence[MessageTypes],
    sync_callbacks_by_artifact_name: dict[str, Callable[[], Any]],
) -> None:
    """Persist this batch of messages and queue artifact-sync callbacks.

    Per-message publish callbacks and per-artifact sync callbacks are queued
    on the same transaction (post-commit hooks fire in registration order).
    For each ``UpdatedArtifactAgentMessage``, the artifact's sync callback is
    queued *immediately before* the message's publish callback — that way the
    on-disk task-sync file is written by the time the frontend receives the
    update notification and fetches ``/artifacts/{name}``, closing the
    SCU-1295 race. Non-artifact messages publish unblocked.
    """
    if not new_messages and not sync_callbacks_by_artifact_name:
        return

    with services.data_model_service.open_task_transaction() as transaction:
        registered_sync_names: set[str] = set()
        for message in new_messages:
            if isinstance(message, UpdatedArtifactAgentMessage):
                name = message.artifact.name
                sync_callback = sync_callbacks_by_artifact_name.get(name)
                if sync_callback is not None and name not in registered_sync_names:
                    transaction.add_callback(sync_callback)
                    registered_sync_names.add(name)
            services.task_service.create_message(message, task_id, transaction)

        # Defensive: any sync callback whose UpdatedArtifactAgentMessage isn't
        # in this batch still gets registered, so the file is written. Should
        # not happen in practice — sync_artifacts only emits callbacks for
        # artifacts it observed in ``new_messages``.
        for name, callback in sync_callbacks_by_artifact_name.items():
            if name not in registered_sync_names:
                transaction.add_callback(callback)


MessageT = TypeVar("MessageT")


def _get_input_messages(message_queue: Queue[MessageT], max_wait_time: float) -> list[MessageT]:
    """
    Get user messages from the queue, waiting for up to `max_wait_time` seconds.

    Returns a list of messages.
    """
    messages = []
    while message_queue.qsize() > 0:
        message = message_queue.get(block=False)
        messages.append(message)
    try:
        message = message_queue.get(timeout=max_wait_time)
    except Empty:
        pass
    else:
        messages.append(message)
    return messages
