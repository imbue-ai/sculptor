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
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
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
from sculptor.interfaces.agents.errors import AgentClientError
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
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.tasks.handlers.run_agent.setup import finalize_task_setup
from sculptor.tasks.handlers.run_agent.setup import load_initial_task_state
from sculptor.tasks.handlers.run_agent.setup import message_queue_subscription_context
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
                        input_message_queue, task_state, shutdown_event
                    )

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
    """
    # state: these variables are changed as the agent runs
    shutdown_started_at: float | None = None
    # we process the user input messages one at a time
    # there are other messages from the user besides PersistentUserMessage, but the other ones are control flow
    # and have nothing to do with snapshotting
    user_input_message_being_processed: PersistentUserMessage | None = None
    queued_user_input_messages: list[PersistentUserMessageUnion] = list(re_queued_messages)
    # is set below from old messages
    last_user_chat_message_id: AgentMessageID | None = None
    # track the full history of persistent messages we've seen
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage] = []
    # tracks whether the agent has asked a question that hasn't been answered yet;
    # while True, queued messages must not be dequeued — only the answer should be sent
    is_waiting_for_question_answer: bool = False
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

        # make sure that we've synced anything that happened previously
        # this ensures that we reach a consistent state once the task has been resumed
        with services.data_model_service.open_task_transaction() as transaction:
            all_messages = services.task_service.get_saved_messages_for_task(task.object_id, transaction)

        # we need to replay the messages to do a variety of things
        persistent_user_message_by_id: dict[AgentMessageID, PersistentUserMessageUnion] = {}
        # one of those things is to figure out what the last user chat message was that we *started* processing
        # this is in case we never *finished* processing it, so that the agent can resume from where it left off
        initial_in_flight_user_chat_message_id: AgentMessageID | None = None
        # An orphaned answer: a UserQuestionAnswerMessage that was delivered to a
        # now-dead agent process (its RequestStarted is in history) but whose turn
        # never completed cleanly. On resume the agent has already recorded the
        # answer (e.g. pi persists it as a toolResult) and has no open dialog, so
        # re-delivering it raw is a stale dialog the harness skips — dropping the
        # answer and leaving the request perpetually in-flight. Resuming it instead
        # settles that dangling request (see _send_user_input_message).
        initial_in_flight_user_question_answer_message_id: AgentMessageID | None = None
        # Track whether the agent emitted any visible response for the in-flight chat
        # message. If it didn't, there's nothing for Claude to "resume" from — we'd
        # rather just resend the original prompt than send a "continue where you left
        # off" instruction with no prior content. Reset on each new RequestStarted.
        is_partial_agent_response = False
        for message in all_messages:
            # just remember the last chat message from the user (that the agent started processing)
            if isinstance(message, RequestStartedAgentMessage):
                persistent_message = persistent_user_message_by_id.get(message.request_id)
                if persistent_message is not None:
                    if isinstance(persistent_message, ChatInputUserMessage):
                        last_user_chat_message_id = message.request_id
                        initial_in_flight_user_chat_message_id = message.request_id
                        is_partial_agent_response = False
                    elif isinstance(persistent_message, UserQuestionAnswerMessage):
                        initial_in_flight_user_question_answer_message_id = message.request_id
                    # add the user message to the history as well
                    persistent_message_history.append(persistent_user_message_by_id[message.request_id])
            if isinstance(message, PersistentRequestCompleteAgentMessage):
                if message.request_id == initial_in_flight_user_chat_message_id:
                    # it doesn't count if this was from a sigterm
                    was_killed = _get_killed_exit_code(message)
                    if not was_killed:
                        initial_in_flight_user_chat_message_id = None
                # Only a clean (non-interrupted) success means the answer's turn
                # actually finished — clear it so it isn't resumed. An interrupted
                # success, a failure, or a kill all leave the answer orphaned (its
                # toolResult is recorded but nothing drove the follow-up turn), so
                # keep it for resume.
                if message.request_id == initial_in_flight_user_question_answer_message_id and (
                    isinstance(message, RequestSuccessAgentMessage) and not message.interrupted
                ):
                    initial_in_flight_user_question_answer_message_id = None
            # used above so that we can figure out which user messages started being processed so far
            if isinstance(message, PersistentUserMessage):
                persistent_user_message_by_id[message.message_id] = message
            # remember all messages that have been emitted so far by the agent
            if isinstance(message, PersistentAgentMessage):
                was_killed = _get_killed_exit_code(message)
                if not was_killed:
                    persistent_message_history.append(message)
                # A ResponseBlockAgentMessage from the in-flight turn means Claude
                # produced visible content that we'd want to continue from on resume.
                if isinstance(message, ResponseBlockAgentMessage):
                    is_partial_agent_response = True
        # If we didn't observe any partial response from the agent, there's nothing
        # to "continue from" — clear the in-flight ID so the message gets pushed as
        # a fresh ChatInputUserMessage rather than a ResumeAgentResponseRunnerMessage.
        # When there IS a partial response, keep the ID so _send_user_input_message
        # converts the push into a resume and Claude continues its --resume session.
        if not is_partial_agent_response:
            initial_in_flight_user_chat_message_id = None

        logger.debug("Initial in-flight user chat message ID: {}", initial_in_flight_user_chat_message_id)
        logger.debug("Last processed message id:              {}", task_state.last_processed_message_id)

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
                    task_state,
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
                task_state,
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
                is_waiting_for_question_answer = True
            elif is_waiting_for_question_answer and isinstance(
                message, (RequestFailureAgentMessage, RequestStoppedAgentMessage)
            ):
                # SCU-530: the agent's chat request failed or was stopped while we
                # were still waiting for an answer to an AUQ — the CLI consumer of
                # that answer is gone, so stop waiting. Without this, subsequent
                # ChatInputUserMessages match the guard at line 624 and get silently
                # appended to ``queued_user_input_messages`` forever.
                is_waiting_for_question_answer = False

        # add any persistent messages to our history
        for message in new_messages:
            if isinstance(message, PersistentAgentMessage):
                killed_exit_code = _get_killed_exit_code(message)
                if killed_exit_code:
                    logger.debug("Agent seems like it exited, returning")
                    return _handle_completed_agent(
                        agent_wrapper,
                        killed_exit_code,
                        task,
                        task_state,
                        project,
                        environment,
                        services,
                    )
                else:
                    persistent_message_history.append(message)

        # Advance the dedup cursor for any completion in this batch. Catches
        # in-flight chat completions, queued-answer completions, and the AUQ-pending
        # case where the in-flight chat ID isn't reflected in
        # user_input_message_being_processed (cleared at v1.py:600 by design).
        task_state = _record_latest_completion_in_state(new_messages, task.object_id, task_state, services)

        # Persist any model catalog the agent surfaced this batch (pi emits one at
        # start) onto task state so the harness's get_available_models reads it.
        task_state = _record_available_models_in_state(new_messages, task.object_id, task_state, services)

        # Did the currently-pending in-flight message complete? Drives the dispatch
        # decision below — distinct from the cursor advance above, which fires for
        # any completion in this batch (including ones for messages other than the
        # one tracked by user_input_message_being_processed).
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
        if is_agent_turn_finished or is_waiting_for_question_answer:
            if is_waiting_for_question_answer:
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
                    is_waiting_for_question_answer = False
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
                if is_waiting_for_question_answer and not isinstance(message, UserQuestionAnswerMessage):
                    # While the agent is waiting for a question answer, queue all other
                    # messages — only the answer should be sent to the agent.
                    queued_user_input_messages.append(message)
                elif user_input_message_being_processed is None:
                    if isinstance(message, UserQuestionAnswerMessage):
                        is_waiting_for_question_answer = False
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


def _get_killed_exit_code(message: Message) -> int:
    if isinstance(message, RequestStoppedAgentMessage):
        causal_error = message.error.construct_instance()
        # sigterm and signint
        if isinstance(causal_error, AgentClientError) and causal_error.exit_code in (
            SIGTERM_EXIT_CODES | SIGINT_EXIT_CODES
        ):
            # exit_code is a member of a set of ints here, so it cannot be None
            # pyrefly: ignore [bad-return]
            return causal_error.exit_code
    return 0


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
    `_fetch_models_into_state` has not run and the task carries no
    `available_models` — the switcher then shows the built-in Claude list. Here,
    once the environment is ready, we run a short-lived pi probe
    (`PiAgent.fetch_available_models_probe`) and persist its curated catalog onto
    task state so the switcher reflects pi's models immediately.

    Returns the task state, evolved with the catalog when the probe found one, so
    the caller carries it forward — otherwise `finalize_task_setup`'s later
    evolve-and-upsert (from the in-memory state) would write the catalog back
    out. Restricted to pi: the `supports_model_selection` check skips harnesses
    that cannot select a model at all, and the `PiAgent` check below skips the
    rest — only pi sources a dynamic catalog via the probe (Claude supports model
    selection but with a static built-in list). Best-effort: on any failure the
    probe returns an empty catalog and the task state is returned unchanged, so
    the switcher falls back exactly as before.
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
    if not available_models and current_model is None:
        return task_state
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
    task_state: AgentTaskStateV2,
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

    # Same per-iteration cursor advance the main loop does after its own _save_messages
    # call — applied here for the final batch of messages popped after the loop exits.
    _record_latest_completion_in_state(new_messages, task.object_id, task_state, services)

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


def _record_latest_completion_in_state(
    new_messages: Sequence[Message],
    task_id: TaskID,
    task_state: AgentTaskStateV2,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Bump last_processed_message_id to the latest completion's request_id in new_messages.

    Single source of truth for advancing the dedup cursor when the agent reaches a
    terminal state for a user message. Called from both the main loop (after
    _save_messages) and _handle_completed_agent (for its post-pop save). The wrapper
    constructs every PersistentRequestCompleteAgentMessage with request_id = the
    user message ID it was wrapping, so request_id alone identifies which user
    message was processed — we don't need to cross-reference the loop's mutable
    user_input_message_being_processed local, which the AUQ-pending state
    intentionally clears to None at v1.py:600 while the chat message is still in
    flight.

    BUT — the wrapper's ``_handle_user_message`` is also invoked for the
    ephemeral ``StopAgentUserMessage`` (and ``InterruptProcessUserMessage`` via
    the same code path), and it emits a completion for those too. Their
    message_ids are never persisted, so blindly setting
    last_processed_message_id to such a request_id would make the NEXT run's
    ``_drop_already_processed_messages`` walk the replay queue looking for an
    ID that isn't there and raise. Filter to request_ids that resolve to a
    persisted user message in the DB.

    Does NOT filter interrupted/killed completions here — the runtime cursor must
    advance for those too (otherwise dedup re-delivers them on the next agent run).
    The startup reconciliation in setup.py applies a different policy (skip
    interrupted) because its semantics differ: it's healing past state, and
    treating an interrupted completion as "done" would lose still-pending input
    (see post-answer-shutdown — hypothesis #12).
    """
    completion_request_ids: list[AgentMessageID] = []
    for message in new_messages:
        if isinstance(message, PersistentRequestCompleteAgentMessage):
            completion_request_ids.append(message.request_id)
    if not completion_request_ids:
        return task_state

    # Resolve which request_ids actually correspond to persisted user messages.
    with services.data_model_service.open_task_transaction() as transaction:
        all_messages = services.task_service.get_saved_messages_for_task(task_id, transaction)
    persistent_user_message_ids = {m.message_id for m in all_messages if isinstance(m, PersistentUserMessage)}

    latest_persisted_request_id: AgentMessageID | None = None
    for request_id in completion_request_ids:
        if request_id in persistent_user_message_ids:
            latest_persisted_request_id = request_id
    if latest_persisted_request_id is None:
        return task_state

    return _update_task_state(
        last_processed_input_message_id=latest_persisted_request_id,
        task_id=task_id,
        task_state=task_state,
        services=services,
    )


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
    the batch carries none. Preserves the DB title like `_update_task_state`, so a
    concurrent rename is not clobbered.
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


def _update_task_state(
    last_processed_input_message_id: AgentMessageID,
    task_id: TaskID,
    task_state: AgentTaskStateV2,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Update the task state with the message ID that was processed successfully."""
    if task_state.last_processed_message_id == last_processed_input_message_id:
        return task_state

    logger.debug(
        f"Updating last processed message ID from {task_state.last_processed_message_id} to {last_processed_input_message_id}"
    )
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task_id)
        assert task_row is not None
        # Read the current DB title so we don't clobber a concurrent rename.
        db_state = AgentTaskStateV2.model_validate(task_row.current_state)
        mutable_task_state = evolver(task_state)
        assign(mutable_task_state.last_processed_message_id, lambda: last_processed_input_message_id)
        assign(mutable_task_state.title, lambda: db_state.title)
        updated_task_state = chill(mutable_task_state)
        task_row = task_row.evolve(task_row.ref().current_state, updated_task_state.model_dump())
        _task_row = transaction.upsert_task(task_row)

    return updated_task_state


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
