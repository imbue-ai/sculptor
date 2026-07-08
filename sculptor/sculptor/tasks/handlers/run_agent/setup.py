import time
from contextlib import contextmanager
from queue import Queue
from typing import Generator
from typing import cast

from loguru import logger

from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.errors import ImbueError
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.nested_evolver import assign
from sculptor.foundation.nested_evolver import chill
from sculptor.foundation.nested_evolver import evolver
from sculptor.interfaces.agents.agent import PersistentRequestCompleteAgentMessage
from sculptor.interfaces.agents.agent import PersistentUserMessageUnion
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
from sculptor.state.messages import PersistentUserMessage
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
    task_state: AgentTaskStateV2,
    shutdown_event: ReadOnlyEvent,
) -> tuple[tuple[PersistentUserMessageUnion, ...], ChatInputUserMessage]:
    """Wait for the initial user message and process already-queued messages.

    Returns (re_queued_messages, initial_message).
    """
    initial_message = _wait_for_initial_user_message(
        user_message_queue=cast(Queue[Message], input_message_queue),
        shutdown_event=shutdown_event,
    )

    # Discard already processed messages
    _, re_queued_messages = _drop_already_processed_messages(
        task_state.last_processed_message_id, cast(Queue[Message], input_message_queue)
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

        # Reconcile last_processed_message_id with persisted message history.
        # The v1 loop's success path commits _save_messages (the agent's completion
        # message) and _update_task_state (the last_processed cursor) in separate
        # transactions. A SIGKILL / OOM / power loss between those two writes leaves
        # the DB with a persisted completion but a stale last_processed cursor, which
        # makes _drop_already_processed_messages leave the message in the queue and
        # the loop re-deliver it to Claude on the next agent run.
        #
        # The reconciliation is to scan all persisted messages, find the latest user
        # message whose message_id matches a request_id on any
        # PersistentRequestCompleteAgentMessage, and treat that as the effective
        # last_processed. Then persist the correction in this same transaction so
        # downstream dedup sees it.
        reconciled_state = _reconcile_last_processed_from_history(task_state, task.object_id, services)
        if reconciled_state.last_processed_message_id != task_state.last_processed_message_id:
            task_state = reconciled_state
            task_row = task_row.evolve(task_row.ref().current_state, task_state.model_dump())
            transaction.upsert_task(task_row)
    return task_state, project


def _is_truly_processed_completion(message: PersistentRequestCompleteAgentMessage) -> bool:
    """True iff this completion represents the agent actually finishing the user message.

    Interrupted / killed completions (``RequestSuccessAgentMessage(interrupted=True)``,
    ``RequestStoppedAgentMessage`` — always emitted on SIGTERM/SIGINT) do NOT count,
    because the agent didn't really finish processing the message. If we counted them
    here, dedup would treat the message as processed and silently drop it on the next
    run — which loses the user's typed input in the post-answer-shutdown scenario.

    ``RequestFailureAgentMessage`` and ``RequestSkippedAgentMessage`` do count: the
    agent received the message and reached a terminal state for it (failed or
    intentionally skipped). Re-delivering would just hit the same outcome.
    """
    if isinstance(message, RequestStoppedAgentMessage):
        return False
    if isinstance(message, RequestSuccessAgentMessage) and message.interrupted:
        return False
    return True


def _reconcile_last_processed_from_history(
    task_state: AgentTaskStateV2,
    task_id: TaskID,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Return task_state with last_processed_message_id derived from message history.

    Walks the persisted messages for this task, finds the latest user message whose
    ``message_id`` matches some ``PersistentRequestCompleteAgentMessage.request_id``
    where the completion represents truly-finished processing (see
    ``_is_truly_processed_completion``), and uses that as the effective
    ``last_processed_message_id``. Only upgrades the cursor (never downgrades), so a
    stale persisted value heals to the truth from the message log without ever
    moving backward.
    """
    with services.data_model_service.open_task_transaction() as transaction:
        all_messages = services.task_service.get_saved_messages_for_task(task_id, transaction)

    completed_request_ids: set[AgentMessageID] = set()
    for message in all_messages:
        if isinstance(message, PersistentRequestCompleteAgentMessage) and _is_truly_processed_completion(message):
            completed_request_ids.add(message.request_id)

    latest_completed_user_message_id: AgentMessageID | None = None
    for message in all_messages:
        if isinstance(message, PersistentUserMessage) and message.message_id in completed_request_ids:
            latest_completed_user_message_id = message.message_id

    if latest_completed_user_message_id is None:
        return task_state
    current = task_state.last_processed_message_id
    if current is not None and str(latest_completed_user_message_id) <= str(current):
        # Don't downgrade — current cursor is already at or ahead of what history shows.
        return task_state
    logger.debug(
        "Reconciled last_processed_message_id from {} to {} based on persisted completions",
        current,
        latest_completed_user_message_id,
    )
    mutable = evolver(task_state)
    assign(mutable.last_processed_message_id, lambda: latest_completed_user_message_id)
    return chill(mutable)


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
