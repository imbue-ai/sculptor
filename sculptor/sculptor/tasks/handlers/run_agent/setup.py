import time
from contextlib import contextmanager
from queue import Queue
from typing import Generator
from typing import Sequence
from typing import cast

from loguru import logger

from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.errors import ImbueError
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.interfaces.agents.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.agent import PersistentUserMessageUnion
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.constants import SIGINT_EXIT_CODES
from sculptor.interfaces.agents.constants import SIGTERM_EXIT_CODES
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.primitives.ids import AgentMessageID
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
from sculptor.state.messages import PersistentAgentMessage
from sculptor.state.messages import PersistentUserMessage
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.utils.type_utils import extract_leaf_types

# it will take at most this much time to notice when the process has finished
_POLL_SECONDS: float = 1.0


class LastProcessedMessageNotInQueueError(ImbueError):
    """Raised when the persisted last-processed message id is absent from the input queue."""


@contextmanager
def message_queue_subscription_context(
    task: Task, services: ServiceCollectionForTask
) -> Generator[
    Queue[UserMessageUnion | ResumeAgentResponseRunnerMessage],
    None,
    None,
]:
    """Subscribe to the message queue without blocking on the initial message."""
    with services.task_service.subscribe_to_user_and_sculptor_system_messages(task.object_id) as input_message_queue:
        yield input_message_queue


def wait_for_initial_message_and_process_queue(
    input_message_queue: Queue[UserMessageUnion | ResumeAgentResponseRunnerMessage],
    last_processed_message_id: AgentMessageID | None,
    shutdown_event: ReadOnlyEvent,
) -> tuple[tuple[PersistentUserMessageUnion, ...], ChatInputUserMessage]:
    """Wait for the initial user message and process already-queued messages.

    ``last_processed_message_id`` is the dedup cursor derived by
    ``scan_message_history``; the replayed queue is consumed up to and including it.

    Returns (re_queued_messages, initial_message).
    """
    initial_message = _wait_for_initial_user_message(
        user_message_queue=cast(Queue[Message], input_message_queue),
        shutdown_event=shutdown_event,
    )

    # Discard already processed messages
    _, re_queued_messages = _drop_already_processed_messages(
        last_processed_message_id, cast(Queue[Message], input_message_queue)
    )

    leaf_persistent_user_message_types = extract_leaf_types(PersistentUserMessageUnion)
    assert all(isinstance(message, leaf_persistent_user_message_types) for message in re_queued_messages)
    assert isinstance(re_queued_messages, tuple)
    re_queued_messages = cast(tuple[PersistentUserMessageUnion, ...], re_queued_messages)

    return re_queued_messages, initial_message


def load_initial_task_state(services: ServiceCollectionForTask, task: Task) -> tuple[AgentTaskStateV2, Project]:
    logger.debug("loading initial task state")
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task.object_id)
        assert task_row is not None, "Task must exist in the database"
        if task_row.current_state is None:
            # Tasks are created with current_state in start_task(), so this should never happen.
            raise RuntimeError(f"Task {task.object_id} has no current_state. All tasks must have initial state.")
        logger.debug("loading existing task state...")
        task_state = AgentTaskStateV2.model_validate(task_row.current_state)
        # load the project so that we can figure out the repo path as well
        project = transaction.get_project(task.project_id)
        assert project is not None, "Project must exist in the database"
    return task_state, project


class HistoryScan(FrozenModel):
    """Startup state replayed from a task's persisted message log.

    Computed once per run by ``scan_message_history`` before the agent starts;
    ``_run_agent_in_environment`` consumes it instead of re-reading the log.
    """

    # The chat message a previous run started processing but never finished, which
    # the loop resumes instead of re-sending (None when there is nothing to resume).
    in_flight_chat_message_id: AgentMessageID | None
    # An orphaned answer: a UserQuestionAnswerMessage that was delivered to a
    # now-dead agent process (its RequestStarted is in history) but whose turn
    # never completed cleanly. On resume the agent has already recorded the
    # answer (e.g. pi persists it as a toolResult) and has no open dialog, so
    # re-delivering it raw is a stale dialog the harness skips — dropping the
    # answer and leaving the request perpetually in-flight. Resuming it instead
    # settles that dangling request (see _send_user_input_message).
    in_flight_answer_message_id: AgentMessageID | None
    # Whether the agent emitted any visible response for the in-flight chat message.
    is_partial_agent_response: bool
    # The last started chat message with no terminal completion the replay accepts,
    # regardless of partial output. Distinct from in_flight_chat_message_id, which
    # additionally requires partial output (there must be something to resume from):
    # a crash before any output leaves the request dangling but not resumable, and
    # the orphan synthesis must still terminalize it or the frontend stays
    # "thinking" forever.
    dangling_chat_message_id: AgentMessageID | None
    # The last user chat message the agent started processing.
    last_user_chat_message_id: AgentMessageID | None
    # Every persistent message replayed in log order: user messages the agent
    # started processing plus the agent's own non-killed messages. The loop keeps
    # appending to (a copy of) this as the run produces more messages.
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage]
    # The dedup cursor: the latest settled user message in log order (None when
    # nothing is settled). _drop_already_processed_messages consumes the replayed
    # queue up to and including this id on restart.
    last_processed_message_id: AgentMessageID | None


def scan_message_history(all_messages: Sequence[Message]) -> HistoryScan:
    """Replay a task's persisted message log to reconstruct the loop's startup state.

    The scan is the single authority on which persisted user messages are settled
    versus still in flight after a restart: a user message is settled iff some
    ``RequestStartedAgentMessage`` references it and the scan does not leave it in
    flight. ``last_processed_message_id`` is derived from the same pass state as
    the in-flight ids, so the dedup cursor and the resume tracking cannot diverge.
    """
    persistent_user_message_by_id: dict[AgentMessageID, PersistentUserMessage] = {}
    # ids of user messages some RequestStartedAgentMessage references — i.e. user
    # messages the agent started processing at some point
    started_user_message_ids: set[AgentMessageID] = set()
    # the last user chat message that we *started* processing — tracked in case we
    # never *finished* processing it, so that the agent can resume where it left off
    last_user_chat_message_id: AgentMessageID | None = None
    in_flight_chat_message_id: AgentMessageID | None = None
    in_flight_answer_message_id: AgentMessageID | None = None
    # Track whether the agent emitted any visible response for the in-flight chat
    # message. If it didn't, there's nothing for Claude to "resume" from — we'd
    # rather just resend the original prompt than send a "continue where you left
    # off" instruction with no prior content. Reset on each new RequestStarted.
    is_partial_agent_response = False
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage] = []
    for message in all_messages:
        # just remember the last chat message from the user (that the agent started processing)
        if isinstance(message, RequestStartedAgentMessage):
            persistent_message = persistent_user_message_by_id.get(message.request_id)
            if persistent_message is not None:
                started_user_message_ids.add(message.request_id)
                if isinstance(persistent_message, ChatInputUserMessage):
                    last_user_chat_message_id = message.request_id
                    in_flight_chat_message_id = message.request_id
                    is_partial_agent_response = False
                elif isinstance(persistent_message, UserQuestionAnswerMessage):
                    in_flight_answer_message_id = message.request_id
                # add the user message to the history as well
                persistent_message_history.append(persistent_message)
        if isinstance(message, PersistentRequestCompleteAgentMessage):
            if message.request_id == in_flight_chat_message_id:
                # it doesn't count if this was from a sigterm
                was_killed = get_killed_exit_code(message)
                if not was_killed:
                    in_flight_chat_message_id = None
            # A clean (non-interrupted) success means the answer's turn
            # actually finished, and a turn_abandoned success means it was
            # terminally settled (harness finalization or pi resume-settle)
            # — clear it either way so it isn't resumed again. A plain
            # interrupted success, a failure, or a kill all leave the answer
            # orphaned (its toolResult is recorded but nothing drove the
            # follow-up turn), so keep it for resume.
            if message.request_id == in_flight_answer_message_id and (
                isinstance(message, RequestSuccessAgentMessage) and (not message.interrupted or message.turn_abandoned)
            ):
                in_flight_answer_message_id = None
        # used above so that we can figure out which user messages started being processed so far
        if isinstance(message, PersistentUserMessage):
            persistent_user_message_by_id[message.message_id] = message
        # remember all messages that have been emitted so far by the agent
        if isinstance(message, PersistentAgentMessage):
            was_killed = get_killed_exit_code(message)
            if not was_killed:
                persistent_message_history.append(message)
            # A ResponseBlockAgentMessage from the in-flight turn means Claude
            # produced visible content that we'd want to continue from on resume.
            if isinstance(message, ResponseBlockAgentMessage):
                is_partial_agent_response = True
    # The pre-gate value: dangling means "no accepted terminal completion", even
    # when there is no partial output to resume from.
    dangling_chat_message_id = in_flight_chat_message_id
    # If we didn't observe any partial response from the agent, there's nothing
    # to "continue from" — clear the in-flight ID so the message gets pushed as
    # a fresh ChatInputUserMessage rather than a ResumeAgentResponseRunnerMessage.
    # When there IS a partial response, keep the ID so _send_user_input_message
    # converts the push into a resume and Claude continues its --resume session.
    if not is_partial_agent_response:
        in_flight_chat_message_id = None

    # Derive the dedup cursor: the latest user message (in log order) that was
    # started and did not end the scan in flight. In-flight messages stay ahead of
    # the cursor so the restart queue re-delivers them for resume; messages that
    # were never started are not settled either.
    last_processed_message_id: AgentMessageID | None = None
    for user_message_id in persistent_user_message_by_id:
        if user_message_id not in started_user_message_ids:
            continue
        if user_message_id in (in_flight_chat_message_id, in_flight_answer_message_id):
            continue
        last_processed_message_id = user_message_id

    return HistoryScan(
        in_flight_chat_message_id=in_flight_chat_message_id,
        in_flight_answer_message_id=in_flight_answer_message_id,
        is_partial_agent_response=is_partial_agent_response,
        dangling_chat_message_id=dangling_chat_message_id,
        last_user_chat_message_id=last_user_chat_message_id,
        persistent_message_history=persistent_message_history,
        last_processed_message_id=last_processed_message_id,
    )


def get_killed_exit_code(message: Message) -> int:
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


def _drop_already_processed_messages(
    last_processed_input_message_id: AgentMessageID | None,
    user_message_queue: Queue[Message],
) -> tuple[tuple[Message, ...], tuple[Message, ...]]:
    """
    Drops all user messages that have already been processed by the agent.
    Return the dropped messages as well as the messages that will be re-queued.
    """
    # catch up, if necessary, to where we were last time
    dropped_messages: list[Message] = []
    found_last_processed_input_message = False
    if last_processed_input_message_id is not None:
        # Consume all messages up to the last processed one
        while not user_message_queue.empty():
            message = user_message_queue.get()
            dropped_messages.append(message)
            if message.message_id == last_processed_input_message_id:
                found_last_processed_input_message = True
                break
        if not found_last_processed_input_message:
            raise LastProcessedMessageNotInQueueError(
                f"Unable to find last processed message in queue: {last_processed_input_message_id}"
            )

        # And then consume all ephemeral messages until the next message that needs to be processed
        while not user_message_queue.empty():
            if user_message_queue.queue and user_message_queue.queue[0].is_ephemeral:
                dropped_message = user_message_queue.get()
                dropped_messages.append(dropped_message)
                logger.debug(f"Dropping ephemeral message after restart: {dropped_message}")
            else:
                break

    # remove all ephemeral messages up to the last stop agent user message
    last_stop_agent_user_message_id = None
    for message in reversed(user_message_queue.queue):
        if isinstance(message, StopAgentUserMessage):
            last_stop_agent_user_message_id = message.message_id
            break

    re_queued_messages: list[Message] = []
    if last_stop_agent_user_message_id is not None:
        while not user_message_queue.empty():
            message = user_message_queue.get()
            if message.is_ephemeral:
                dropped_messages.append(message)
            else:
                re_queued_messages.append(message)
            if message.message_id == last_stop_agent_user_message_id:
                break
    return tuple(dropped_messages), tuple(re_queued_messages)


def _wait_for_initial_user_message(
    user_message_queue: Queue[Message], shutdown_event: ReadOnlyEvent
) -> ChatInputUserMessage:
    """
    Waits for the first user message in the queue.
    """
    while True:
        if shutdown_event.is_set():
            raise UserPausedTaskError()
        for i in range(user_message_queue.qsize() - 1, -1, -1):
            message = user_message_queue.queue[i]
            if isinstance(message, ChatInputUserMessage):
                return message
        time.sleep(_POLL_SECONDS)
