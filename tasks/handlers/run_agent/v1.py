import datetime
import time
from pathlib import Path
from queue import Empty
from queue import Queue
from typing import Any
from typing import Callable
from typing import Sequence
from typing import assert_never

from loguru import logger
from pydantic import AnyUrl

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import is_live_debugging
from imbue_core.constants import ExceptionPriority
from imbue_core.errors import ExpectedError
from imbue_core.nested_evolver import assign
from imbue_core.nested_evolver import chill
from imbue_core.nested_evolver import evolver
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import PersistentAgentMessage
from imbue_core.sculptor.state.messages import PersistentUserMessage
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from imbue_core.serialization import SerializedException
from sculptor.agents.claude_code_sdk.agent import ClaudeCodeSDKAgent
from sculptor.agents.claude_code_sdk.errors import ClaudeClientError
from sculptor.agents.claude_code_text.agent import ClaudeCodeTextAgent
from sculptor.agents.hello_agent.agent import HelloAgent
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import NotificationImportance
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
from sculptor.interfaces.agents.v1.agent import AGENT_EXIT_CODE_FROM_SIGINT
from sculptor.interfaces.agents.v1.agent import AGENT_EXIT_CODE_FROM_SIGTERM
from sculptor.interfaces.agents.v1.agent import Agent
from sculptor.interfaces.agents.v1.agent import AgentConfigTypes
from sculptor.interfaces.agents.v1.agent import AgentCrashedRunnerMessage
from sculptor.interfaces.agents.v1.agent import AgentSnapshotRunnerMessage
from sculptor.interfaces.agents.v1.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.v1.agent import ClaudeCodeTextAgentConfig
from sculptor.interfaces.agents.v1.agent import EnvironmentCrashedRunnerMessage
from sculptor.interfaces.agents.v1.agent import FileAgentArtifact
from sculptor.interfaces.agents.v1.agent import HelloAgentConfig
from sculptor.interfaces.agents.v1.agent import KilledAgentRunnerMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncUpdateCompletedMessage
from sculptor.interfaces.agents.v1.agent import ManualSyncMergeIntoAgentAttemptedMessage
from sculptor.interfaces.agents.v1.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.v1.agent import PersistentRunnerMessage
from sculptor.interfaces.agents.v1.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.v1.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.v1.agent import StopAgentUserMessage
from sculptor.interfaces.agents.v1.agent import TMUX_OUTPUT_ARTIFACT_NAME
from sculptor.interfaces.agents.v1.agent import UnexpectedErrorRunnerMessage
from sculptor.interfaces.agents.v1.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.v1.agent import WarningRunnerMessage
from sculptor.interfaces.agents.v1.errors import AgentCrashed
from sculptor.interfaces.agents.v1.errors import UncleanTerminationAgentError
from sculptor.interfaces.agents.v1.errors import WaitTimeoutAgentError
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.interfaces.environments.v1.constants import AGENT_DATA_PATH
from sculptor.interfaces.environments.v1.errors import EnvironmentFailure
from sculptor.primitives.ids import UserReference
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.task_service.api import TaskService
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import TaskError
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.services.task_service.errors import UserStoppedTaskError
from sculptor.tasks.handlers.run_agent.checks.check_process_controller import CheckProcessController
from sculptor.tasks.handlers.run_agent.setup import branch_prediction_context
from sculptor.tasks.handlers.run_agent.setup import environment_setup_context
from sculptor.tasks.handlers.run_agent.setup import finalize_git_setup
from sculptor.tasks.handlers.run_agent.setup import load_initial_task_state
from sculptor.tasks.handlers.run_agent.setup import message_queue_context
from sculptor.utils.timeout import log_runtime

# it will take at most this much time to notice when the process has finished
_POLL_SECONDS: float = 1.0
# how long to wait for the agent to shut down after the user has requested it (before killing it)
_MAX_SOFT_SHUTDOWN_SECONDS: float = 10.0
# how long to wait when hard killing the agent after the soft shutdown has been requested
_MAX_HARD_SHUTDOWN_SECONDS: float = 10.0


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


class UnknownAgentConfigError(ExpectedError):
    pass


def run_agent_task_v1(
    task_data: AgentTaskInputsV1,
    task: Task,
    services: ServiceCollectionForTask,
    task_deadline: datetime.datetime | None,
    settings: SculptorSettings,
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
    try:
        logger.debug("running task")
        setup_start_time = time.monotonic()

        # Load task state and project
        task_state, project = load_initial_task_state(services, task)

        # Set up message queue and get initial messages
        with message_queue_context(task, task_state, services) as (input_message_queue, initial_message, fork_message):
            # Start branch prediction if needed
            with branch_prediction_context(task, task_state, initial_message, project, services, settings) as (
                title_and_branch_container,
                title_thread,
            ):
                # Load secrets
                secrets = services.secrets_service.get_secrets(task_data.available_secrets)

                # Set up environment
                with environment_setup_context(project, task, task_data, task_state, services, secrets) as (
                    environment,
                    task_state,
                ):
                    # Handle git initialization and branch setup
                    task_state = finalize_git_setup(
                        task=task,
                        task_state=task_state,
                        environment=environment,
                        fork_message=fork_message,
                        title_thread=title_thread,
                        title_and_branch_container=title_and_branch_container,
                        initial_message=initial_message,
                        project=project,
                        task_data=task_data,
                        services=services,
                    )

                    logger.debug("TIMING LOG: {} took {}s to run", "task setup", time.monotonic() - setup_start_time)
                    # and run the agent in the environment until it either finishes or the environment dies
                    return _run_agent_in_environment(
                        task=task,
                        task_data=task_data,
                        task_state=task_state,
                        input_message_queue=input_message_queue,
                        environment=environment,
                        services=services,
                        project=project,
                        settings=settings,
                    )

    except Exception as e:
        _on_exception(e, task_id, user_reference, services)
    return None


# TODO: this design can be fairly easily extended to enable direct tool invocations
#  just send a user message, and treat it as an outstanding request
#  it ought to be possible to request to "stop" an invocation as well,
#  The main design question here is how to handle outputs
#  (plain text vs json, how to show in the UI, etc, since generic tools can return anything)
def _run_agent_in_environment(
    task: Task,
    task_data: AgentTaskInputsV1,
    task_state: AgentTaskStateV1,
    input_message_queue: Queue[Message],
    environment: Environment,
    services: ServiceCollectionForTask,
    project: Project,
    settings: SculptorSettings,
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
    queued_user_input_messages: list[PersistentUserMessage] = []
    # track the last message that we handled
    last_processed_input_message_id: AgentMessageID | None = task_state.last_processed_message_id
    # is set below from old messages
    last_user_chat_message_id: AgentMessageID | None = None
    # track the full history of persistent messages we've seen
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage] = []
    # TODO(59a2e379-4304-425f-9ce8-75fd49d262a1): load this from devcontainer.json *when we start the task* and stick it into the task_data
    #  then read it from there
    root_data_path = AGENT_DATA_PATH
    # this handles the loading, running, stopping, and restarting of all checks
    check_controller = CheckProcessController(
        task_id=task.object_id,
        project_id=task.project_id,
        environment=environment,
        services=services,
        root_data_path=root_data_path,
    )
    # FIXME: we'll need to update this mapping whenever local sync makes a new snapshot as well
    # technically the input can be None if we are snapshotting before the first message is sent
    # which can happen if you try to update the system prompt before sending any messages
    snapshot_by_user_chat_message_id: dict[AgentMessageID | None, ImageTypes] = {}

    with log_runtime("run_agent_in_environment pre-processing"):
        # figure out what command we need to run (eg, which agent to invoke)
        in_testing = settings.TESTING.INTEGRATION_ENABLED
        with services.data_model_service.open_task_transaction() as transaction:
            # pyre-fixme[16]: get_all_tasks is only implemented by SQLTransaction, but transaction is TaskAndModelTransaction
            all_tasks = transaction.get_all_tasks()
        snapshot_path = _get_snapshot_by_task(task, all_tasks, settings.TESTING.SNAPSHOT_PATH)
        agent_wrapper = _get_agent_wrapper(
            task_data.agent_config, environment, task.object_id, in_testing=in_testing, snapshot_path=snapshot_path
        )
        secrets = services.secrets_service.get_secrets(task_data.available_secrets)
        anthropic_credentials = services.anthropic_credentials_service.get_anthropic_credentials()
        # assert anthropic_credentials is not None
        # Start agent
        agent_wrapper.start(secrets, anthropic_credentials)

        # make sure that we've synced anything that happened previously
        # this ensures that we reach a consistent state once the task has been resumed
        with services.data_model_service.open_task_transaction() as transaction:
            all_messages = services.task_service.get_saved_messages_for_task(task.object_id, transaction)

        # we need to replay the messages to do a variety of things
        persistent_user_message_by_id = {}
        # one of those things is to figure out what the last user chat message was that we *started* processing
        # this is in case we never *finished* processing it, so that the agent can resume from where it left off
        initial_in_flight_user_chat_message_id: AgentMessageID | None = None
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
                    # add the user message to the history as well
                    persistent_message_history.append(persistent_user_message_by_id[message.request_id])
            if isinstance(message, PersistentRequestCompleteAgentMessage):
                if message.request_id == initial_in_flight_user_chat_message_id:
                    # ok, except it doesn't count if this was from a sigterm
                    was_killed = _get_is_killed_request(message)
                    if not was_killed:
                        initial_in_flight_user_chat_message_id = None
            # build up the mapping of user input message IDs to snapshots so that we can properly re-run checks
            if isinstance(message, AgentSnapshotRunnerMessage):
                snapshot_by_user_chat_message_id[message.for_user_message_id] = message.image
            # used above so that we can figure out which user messages started being processed so far
            if isinstance(message, PersistentUserMessage):
                persistent_user_message_by_id[message.message_id] = message
            # remember all messages that have been emitted so far by the agent
            if isinstance(message, PersistentAgentMessage):
                was_killed = _get_is_killed_request(message)
                if not was_killed:
                    persistent_message_history.append(message)
            if isinstance(message, ResponseBlockAgentMessage):
                is_partial_agent_response = True
        # if we didn't observe any responses from the agent, reset our initial in-flight message ID
        # this will cause us to resend the message to the agent (but there's no visible wasted work, so that should be ok)
        # note that this whole thing is a little bit racey -- we may not have received some messages that the agent thinks that it sent to us
        # FIXME: put this back -- nothing counts as in progress right now
        # if not is_partial_agent_response:
        #     initial_in_flight_user_chat_message_id = None
        initial_in_flight_user_chat_message_id = None

        logger.debug("Initial in-flight user chat message ID: {}", initial_in_flight_user_chat_message_id)
        logger.debug("Last processed message id:              {}", task_state.last_processed_message_id)

    # starts loading any previous check data in a thread, handles cleaning up any check process threads
    with check_controller.start(snapshot_by_user_chat_message_id, task.parent_task_id):
        # consider our last snapshot to be now (so that we can properly make new snapshots if the user starts out with local syncing)
        last_snapshot_time = time.monotonic()
        # track the last time we had a local sync change that modified the filesystem
        last_local_sync_change_time: float | None = None
        # this is the core event loop for the agent.
        exit_code: int | None
        while True:
            # if we have been trying to shut down for too long, it is time for more drastic measures.
            if shutdown_started_at is not None and time.monotonic() - shutdown_started_at > _MAX_SOFT_SHUTDOWN_SECONDS:
                # might as well go see where it is hung if we can...
                kill_time_start = time.monotonic()
                try:
                    agent_wrapper.terminate(_MAX_HARD_SHUTDOWN_SECONDS)
                    remaining_shutdown_time = time.monotonic() - kill_time_start
                    if remaining_shutdown_time < 0:
                        raise UncleanTerminationAgentError("No time left to call wait() on agent wrapper")
                    exit_code = agent_wrapper.wait(remaining_shutdown_time)
                except (UncleanTerminationAgentError, WaitTimeoutAgentError) as e:
                    raise AgentHardKilled(
                        f"Agent took longer than {_MAX_SOFT_SHUTDOWN_SECONDS + _MAX_HARD_SHUTDOWN_SECONDS} seconds to shut down"
                    ) from e
                else:
                    is_dirty = (
                        last_local_sync_change_time is not None or user_input_message_being_processed is not None
                    )
                    return _handle_completed_agent(
                        agent_wrapper,
                        exit_code,
                        task,
                        project,
                        environment,
                        services,
                        is_dirty,
                        last_user_chat_message_id,
                    )

            # if the process has completed
            exit_code = agent_wrapper.poll()
            if exit_code is not None:
                is_dirty = last_local_sync_change_time is not None or user_input_message_being_processed is not None
                return _handle_completed_agent(
                    agent_wrapper, exit_code, task, project, environment, services, is_dirty, last_user_chat_message_id
                )

            # transfer any output from the process
            new_messages = agent_wrapper.pop_messages()
            callbacks = sync_artifacts(
                new_messages, task, project, environment, services.git_repo_service, services.task_service
            )

            # save the new messages off
            _save_messages(task.object_id, services, new_messages, callbacks)

            # add any persistent messages to our history
            for message in new_messages:
                if isinstance(message, PersistentAgentMessage):
                    killed_exit_code = _get_is_killed_request(message)
                    if killed_exit_code:
                        logger.debug("Agent seems like it exited, returning")
                        is_dirty = (
                            last_local_sync_change_time is not None or user_input_message_being_processed is not None
                        )
                        return _handle_completed_agent(
                            agent_wrapper,
                            killed_exit_code,
                            task,
                            project,
                            environment,
                            services,
                            is_dirty,
                            last_user_chat_message_id,
                        )
                    else:
                        persistent_message_history.append(message)

            # check if our currently pending user input message has completed
            # this causes "settling", eg, we want to snapshot the state
            is_settled = False
            is_agent_turn_finished = False
            if user_input_message_being_processed is not None:
                for message in new_messages:
                    if isinstance(message, PersistentRequestCompleteAgentMessage):
                        if message.request_id == user_input_message_being_processed.message_id:
                            is_settled = True
                            is_agent_turn_finished = True
                            # we reset this here because it only matters post-agent message response
                            last_local_sync_change_time = None

            # the other way that "settling" can happen is if we're not even processing a message,
            # but local sync ended up causing our state to change
            _MIN_SNAPSHOT_INTERVAL_SECONDS = 10.0
            _LOCAL_SYNC_CHANGE_DEBOUNCE_SECONDS = 10.0
            is_state_dirty = last_local_sync_change_time is not None
            if is_state_dirty and user_input_message_being_processed is None:
                # we only count ourselves as "settled" if enough time has elapsed since we last snapshotted
                seconds_since_snapshot = time.monotonic() - last_snapshot_time
                if seconds_since_snapshot > _MIN_SNAPSHOT_INTERVAL_SECONDS:
                    # we only consider ourselves as "settled" if it's been long enough since we saw a local sync update
                    seconds_since_local_sync = time.monotonic() - last_local_sync_change_time
                    if seconds_since_local_sync > _LOCAL_SYNC_CHANGE_DEBOUNCE_SECONDS:
                        is_settled = True
                        last_local_sync_change_time = None

            # if the process is settled (all messages have been processed), we can snapshot the state
            if is_settled:
                # update these tracking variables if we've settled because the message finished
                if user_input_message_being_processed is not None:
                    last_processed_input_message_id = user_input_message_being_processed.message_id
                    if isinstance(user_input_message_being_processed, ChatInputUserMessage):
                        last_user_chat_message_id = user_input_message_being_processed.message_id
                # this is where we can actually snapshot the filesystem
                prev_task_state = task_state
                task_state = _update_task_state(
                    last_processed_input_message_id=last_processed_input_message_id,
                    last_user_chat_message_id=last_user_chat_message_id,
                    environment=environment,
                    task_id=task.object_id,
                    task_state=task_state,
                    services=services,
                    is_settled=True,
                )
                is_new_snapshot = prev_task_state.image != task_state.image
                # update our mapping so that we can run checks against it in the future
                if is_new_snapshot:
                    # this can only be None temporarily (until silly old user_setup.sh goes away)
                    if last_user_chat_message_id is not None:
                        snapshot_by_user_chat_message_id[last_user_chat_message_id] = task_state.image
                # send the next message (if there is one waiting)
                if len(queued_user_input_messages) == 0:
                    user_input_message_being_processed = None
                else:
                    user_input_message_being_processed = _send_user_input_message(
                        agent_wrapper,
                        queued_user_input_messages.pop(0),
                        check_controller,
                        initial_in_flight_user_chat_message_id,
                        services,
                        task.object_id,
                    )

            # get any new user message(s)
            user_messages = _get_input_messages(input_message_queue, max_wait_time=_POLL_SECONDS)

            # if we observed a shutdown message, start the timer
            if _is_shutdown_expected(user_messages):
                # TODO: maybe time to hard kill if we get a second one
                if shutdown_started_at is None:
                    shutdown_started_at = time.monotonic()

            # send the user messages to the process
            is_filesystem_modified_by_local_sync = False
            for message in user_messages:
                # handle input chat user messages one at a time
                if isinstance(message, PersistentUserMessage):
                    if user_input_message_being_processed is None:
                        user_input_message_being_processed = _send_user_input_message(
                            agent_wrapper,
                            message,
                            check_controller,
                            initial_in_flight_user_chat_message_id,
                            services,
                            task.object_id,
                        )
                    else:
                        queued_user_input_messages.append(message)
                    # add it to the conversation history
                    persistent_message_history.append(message)
                # let the check controller handle its own messages
                elif check_controller.handle_message(
                    message,
                    current_user_chat_message_id=user_input_message_being_processed.message_id
                    if user_input_message_being_processed
                    and isinstance(user_input_message_being_processed, ChatInputUserMessage)
                    else last_user_chat_message_id,
                    secrets=secrets,
                    snapshot_by_user_input_message_id=snapshot_by_user_chat_message_id,
                ):
                    pass
                # otherwise, simply forward the message to the agent and let it figure it out
                else:
                    # note whether we have seen a local sync message that indicates a change to the filesystem
                    if isinstance(
                        message, (LocalSyncUpdateCompletedMessage, ManualSyncMergeIntoAgentAttemptedMessage)
                    ):
                        is_filesystem_modified_by_local_sync = True
                        last_local_sync_change_time = time.monotonic()
                    # pyre-fixme[6]: the argument type UserMessageUnion is not a superset of Message.
                    agent_wrapper.push_message(message)

            # if local sync caused a change to the filesystem, we need to persist the environment
            #  this is a no-op for Docker and the local filesystem, but modal needs to be notified so that it can snapshot.
            if is_filesystem_modified_by_local_sync:
                environment.persist()

            # if changes have happened (from either local sync or agent turn ending), we need to reload the checks
            if is_agent_turn_finished or is_filesystem_modified_by_local_sync:
                check_controller.on_filesystem_change(
                    is_agent_turn_finished=is_agent_turn_finished,
                    current_user_message_id=user_input_message_being_processed.message_id
                    if user_input_message_being_processed
                    and isinstance(user_input_message_being_processed, ChatInputUserMessage)
                    else last_user_chat_message_id,
                    is_next_message_in_progress=user_input_message_being_processed is not None,
                    snapshot=task_state.image,
                    secrets=secrets,
                    persistent_message_history=persistent_message_history,
                )


def _get_is_killed_request(message: Message) -> int:
    if isinstance(message, RequestStoppedAgentMessage):
        causal_error = message.error.construct_instance()
        # sigterm and signint
        if isinstance(causal_error, ClaudeClientError) and causal_error.exit_code in (
            AGENT_EXIT_CODE_FROM_SIGTERM,
            AGENT_EXIT_CODE_FROM_SIGINT,
        ):
            return causal_error.exit_code
    return 0


def _send_user_input_message(
    agent_wrapper: Agent,
    message: PersistentUserMessage,
    check_controller: CheckProcessController,
    initial_in_flight_user_chat_message_id: AgentMessageID | None,
    services: ServiceCollectionForTask,
    task_id: TaskID,
) -> PersistentUserMessage:
    user_input_message_being_processed = message
    if isinstance(message, ChatInputUserMessage):
        check_controller.on_persistent_user_message(message)
    # if this message was one that we left off on last time,
    # we need to send a special "Please pick up where you left off" message instead of the normal message
    # this allows the agent to use whatever in-flight response it had
    # (which prevents the user from losing a bunch of work if they shut down or sculptor crashed)
    # this is especially important as agents start to have much longer response times
    if user_input_message_being_processed.message_id == initial_in_flight_user_chat_message_id and isinstance(
        user_input_message_being_processed, ChatInputUserMessage
    ):
        resume_message = ResumeAgentResponseRunnerMessage(
            for_user_message_id=user_input_message_being_processed.message_id,
            model_name=user_input_message_being_processed.model_name,
        )
        with services.data_model_service.open_task_transaction() as transaction:
            services.task_service.create_message(message, task_id, transaction)
        agent_wrapper.push_message(resume_message)
    else:
        # pyre-fixme[6]: the argument type UserMessageUnion is not a superset of PersistentUserMessage; the latter is a base type with a potentially unbound number of subclasses
        agent_wrapper.push_message(user_input_message_being_processed)
    return user_input_message_being_processed


def _on_exception(
    e: Exception, task_id: TaskID, user_reference: UserReference, services: ServiceCollectionForTask
) -> None:
    # this "exception" is expected in the sense that it was the user telling the task to stop
    # so it doesn't count as success
    if isinstance(e, AgentPaused):
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
    full_output_url = _get_full_output_url(task_id, services.task_service)
    agent_error_message: PersistentRunnerMessage
    match error:
        case AgentHardKilled():
            agent_error_message = KilledAgentRunnerMessage(
                message_id=AgentMessageID(), full_output_url=full_output_url
            )
            # not worth notifying the user about this, they told it to stop
            is_worth_notifying = False
        case AgentCrashed():
            agent_error_message = AgentCrashedRunnerMessage(
                message_id=AgentMessageID(),
                exit_code=error.exit_code,
                full_output_url=full_output_url,
                error=SerializedException.build(error),
            )
        # TODO: we could transparently retry on these errors (at a lower level)
        #  we would still need to handle them here, but it would only be for repeated failures
        case EnvironmentFailure():
            agent_error_message = EnvironmentCrashedRunnerMessage(
                message_id=AgentMessageID(),
                error=SerializedException.build(error),
                full_output_url=full_output_url,
            )
        case _:
            agent_error_message = UnexpectedErrorRunnerMessage(
                message_id=AgentMessageID(),
                error=SerializedException.build(error),
                full_output_url=full_output_url,
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
                    message=("Agent failed unexpectedly" if is_expected else str(error))
                    + f"\n\nSee full logs: {full_output_url}",
                    importance=NotificationImportance.TIME_SENSITIVE,
                    task_id=task_row.object_id,
                ),
            )

    # raising will ensure that unexpected Exceptions are logged, and that the task is marked as failed
    raise AgentTaskFailure(transaction_callback=on_transaction, is_user_notified=True)


def _get_snapshot_by_task(
    target_task: Task, all_tasks: tuple[Task, ...], snapshot_path: str | None = None
) -> Path | None:
    if snapshot_path is None:
        return None
    for i, task in enumerate([task for task in all_tasks if isinstance(task.input_data, AgentTaskInputsV1)]):
        if task.object_id == target_task.object_id:
            return Path(snapshot_path) / f"task_{i}.llm_cache_db"
    assert False, f"Could not find snapshot for task {target_task}"


def _get_agent_wrapper(
    agent_config: AgentConfigTypes,
    environment: Environment,
    task_id: TaskID,
    in_testing: bool = False,
    snapshot_path: Path | None = None,
) -> Agent:
    if isinstance(agent_config, HelloAgentConfig):
        return HelloAgent(config=agent_config, environment=environment)
    elif isinstance(agent_config, ClaudeCodeSDKAgentConfig):
        return ClaudeCodeSDKAgent(
            config=agent_config,
            environment=environment,
            task_id=task_id,
            in_testing=in_testing,
            snapshot_path=snapshot_path,
        )
    elif isinstance(agent_config, ClaudeCodeTextAgentConfig):
        return ClaudeCodeTextAgent(config=agent_config, environment=environment)
    raise UnknownAgentConfigError(f"Unknown agent config: {agent_config}")


def _handle_completed_agent(
    agent_wrapper: Agent,
    exit_code: int,
    task: Task,
    project: Project,
    environment: Environment,
    services: ServiceCollectionForTask,
    is_dirty: bool,
    last_user_chat_message_id: AgentMessageID | None,
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

    agent_wrapper.wait(10)  # NOTE: if the agent has hit an exception, we will raise it here

    # if dirty, we need to snapshot the environment before shutting down
    # this is only really necessary so that, if we are upgrading sculptor, the user will be able to resume
    # without losing any of their local sync'd work
    if is_dirty and last_user_chat_message_id is not None:
        if exit_code in (AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT, 0):
            try:
                snapshot_image = environment.snapshot()
            except EnvironmentFailure as e:
                log_exception(e, "Failed to snapshot image during shutdown", priority=ExceptionPriority.LOW_PRIORITY)
            else:
                with services.data_model_service.open_task_transaction() as transaction:
                    snapshot_message = AgentSnapshotRunnerMessage(
                        message_id=AgentMessageID(),
                        image=snapshot_image,
                        for_user_message_id=last_user_chat_message_id,
                        is_settled=False,
                    )
                    services.task_service.create_message(snapshot_message, task.object_id, transaction)
                    mutable_task_state = evolver(task.current_state)
                    assign(mutable_task_state.image, lambda: snapshot_image)
                    updated_task_state = chill(mutable_task_state)
                    task = task.evolve(task.ref().current_state, updated_task_state.model_dump())
                    task = transaction.upsert_task(task)

    # if we expected to shut down, and we observed the correct exit code, fine
    if exit_code in (
        AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT,
        AGENT_EXIT_CODE_FROM_SIGINT,
        AGENT_EXIT_CODE_FROM_SIGTERM,
    ):
        raise AgentPaused()
    # if the process was successful, return
    elif exit_code == 0:
        return _on_success(task.object_id, task.user_reference, services.task_service, callbacks)

    # if the process failed
    else:
        raise AgentCrashed(f"Agent died with exit code {exit_code}", exit_code=exit_code)


def _get_full_output_url(task_id: TaskID, task_service: TaskService) -> AnyUrl | None:
    output_url = task_service.get_artifact_file_url(task_id, TMUX_OUTPUT_ARTIFACT_NAME)
    if Path(str(output_url).replace("file://", "")).exists():
        return output_url
    else:
        return None


def _on_success(
    task_id: TaskID, user_reference: UserReference, task_service: TaskService, callbacks: tuple[Callable[[], Any], ...]
) -> Callable[[DataModelTransaction], None]:
    logger.debug("process finished successfully")

    def on_transaction(t: DataModelTransaction) -> None:
        full_output_url = _get_full_output_url(task_id, task_service)

        task_row = task_service.get_task(task_id, t)
        assert task_row is not None
        t.insert_notification(
            Notification(
                user_reference=user_reference,
                object_id=NotificationID(),
                message="Finished running agent"
                + (f"\n\nSee full logs: {full_output_url}" if full_output_url else ""),
                importance=NotificationImportance.ACTIVE,
                task_id=task_row.object_id,
            )
        )
        for callback in callbacks:
            t.add_callback(callback)

    return on_transaction


def sync_artifacts(
    new_messages: Sequence[Message],
    task: Task,
    project: Project,
    environment: Environment,
    git_repo_service: GitRepoService,
    task_service: TaskService,
) -> tuple[Callable[[], Any], ...]:
    # it is important that we pull the messages first --
    # this way we can guarantee that the other artifacts have been written
    # (as long as the agent wrapper does the reverse, not writing the messages until everything else is flushed)
    artifacts_to_sync = [x.artifact for x in new_messages if isinstance(x, UpdatedArtifactAgentMessage)]
    # this is used to ensure that we don't sync the same artifact multiple times
    artifact_names_seen = set()
    callbacks: list[Callable[[], Any]] = []
    for artifact in reversed(artifacts_to_sync):
        if artifact.name in artifact_names_seen:
            logger.trace("skipping artifact {} as it has already been synced", artifact.name)
            continue
        else:
            artifact_names_seen.add(artifact.name)
        match artifact:
            case FileAgentArtifact():
                if artifact.url is None:
                    logger.debug("skipping artifact {} as it has no url", artifact.name)
                    continue
                logger.debug("syncing artifact: {}", artifact.url)
                remote_path = str(artifact.url).replace("file://", "")
                if not environment.exists(remote_path):
                    # TODO: in theory, we should not hit this code path, but let's not make it a hard error just in case
                    log_exception(
                        Exception(f"Artifact {artifact.name} does not exist at {remote_path}"),
                        "Artifact does not exist",
                        priority=ExceptionPriority.MEDIUM_PRIORITY,
                    )
                    if is_live_debugging():
                        raise Exception(f"Artifact {artifact.name} does not exist at {remote_path}")
                    continue
                contents = environment.read_file(remote_path)
                callbacks.append(
                    lambda name=artifact.name, data=contents: task_service.set_artifact_file_data(
                        task.object_id, name, data
                    )
                )
                logger.debug("synced file artifact: {}", remote_path)
            case _ as unreachable:
                assert_never(unreachable)

    return tuple(callbacks)


def _update_task_state(
    last_processed_input_message_id: AgentMessageID,
    last_user_chat_message_id: AgentMessageID,
    environment: Environment,
    task_id: TaskID,
    task_state: AgentTaskStateV1,
    services: ServiceCollectionForTask,
    is_settled: bool,
) -> AgentTaskStateV1:
    """Update the task state with the message ID that was processed successfully."""
    if task_state.last_processed_message_id == last_processed_input_message_id:
        return task_state
    try:
        with log_runtime("Snapshotting image"):
            snapshot_image = environment.snapshot()
    except EnvironmentFailure as e:
        log_exception(e, "Failed to snapshot image", priority=ExceptionPriority.LOW_PRIORITY)
        with services.data_model_service.open_task_transaction() as transaction:
            serialized_error = SerializedException.build(e) if e is not None else None
            warning_message = WarningRunnerMessage(
                message="Failed to snapshot image - this means your latest changes may not be saved.",
                error=serialized_error,
            )
            services.task_service.create_message(warning_message, task_id, transaction)

    logger.debug("Finished snapshotting image: {}", snapshot_image)
    logger.debug(
        f"Updating last processed message ID from {task_state.last_processed_message_id} to {last_processed_input_message_id}"
    )
    with services.data_model_service.open_task_transaction() as transaction:
        snapshot_message = AgentSnapshotRunnerMessage(
            message_id=AgentMessageID(),
            image=snapshot_image,
            for_user_message_id=last_user_chat_message_id,
            is_settled=is_settled,
        )
        services.task_service.create_message(snapshot_message, task_id, transaction)
        task_row = transaction.get_task(task_id)
        mutable_task_state = evolver(task_state)
        assign(mutable_task_state.last_processed_message_id, lambda: last_processed_input_message_id)
        assign(mutable_task_state.image, lambda: snapshot_image)
        assign(mutable_task_state.environment_id, lambda: environment.environment_id)
        updated_task_state = chill(mutable_task_state)
        assert task_row is not None
        task_row = task_row.evolve(task_row.ref().current_state, updated_task_state.model_dump())
        _task_row = transaction.upsert_task(task_row)
        return updated_task_state


def _is_shutdown_expected(observed_messages: list[Message]) -> bool:
    """
    Check if there was a message indicating that the agent should stop.

    These are "soft" stops -- the agent is expected to shut down cleanly within a reasonable time frame.
    """
    for message in observed_messages:
        if isinstance(message, StopAgentUserMessage):
            return True
    return False


def _save_messages(
    task_id: TaskID,
    services: ServiceCollectionForTask,
    new_messages: Sequence[Message],
    callbacks: tuple[Callable[[], Any], ...],
) -> None:
    if not new_messages and not callbacks:
        return

    with services.data_model_service.open_task_transaction() as transaction:
        for message in new_messages:
            services.task_service.create_message(message, task_id, transaction)
        for callback in callbacks:
            transaction.add_callback(callback)


def _get_input_messages(message_queue: Queue[Message], max_wait_time: float) -> list[Message]:
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
