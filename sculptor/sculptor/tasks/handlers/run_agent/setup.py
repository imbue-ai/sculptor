import time
from contextlib import contextmanager
from queue import Queue
from threading import Thread
from typing import Generator
from typing import Sequence
from typing import cast

from loguru import logger

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.errors import ImbueError
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.nested_evolver import assign
from sculptor.foundation.nested_evolver import chill
from sculptor.foundation.nested_evolver import evolver
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.foundation.progress_tracking.progress_tracking import start_finish_context
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.interfaces.agents.agent import ContextClearedMessage
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
from sculptor.interfaces.agents.harness import Harness
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.server.llm_content_generation import TaskTitle
from sculptor.server.llm_content_generation import generate_title_from_prompt
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.task_service.errors import UserPausedTaskError
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
from sculptor.state.messages import PersistentAgentMessage
from sculptor.state.messages import PersistentUserMessage
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.utils.type_utils import extract_leaf_types

# it will take at most this much time to notice when the process has finished
_POLL_SECONDS: float = 1.0
# if it takes longer than this, we give up waiting for the title and branch name to be predicted
_TITLE_NAME_TIMEOUT_SECONDS: float = 10.0
# the fallback title is the initial prompt truncated to this many characters
_FALLBACK_TITLE_MAX_LENGTH: int = 60
_FIXED_TITLE_COUNTER_FOR_TESTING = 0


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


@contextmanager
def title_prediction_context(
    task_state: AgentTaskStateV2,
    initial_message: ChatInputUserMessage,
    settings: SculptorSettings,
    concurrency_group: ConcurrencyGroup,
    root_progress_handle: RootProgressHandle,
) -> Generator[tuple[list[TaskTitle], Thread | None], None, None]:
    """Start title prediction thread if needed."""
    title_result: list[TaskTitle] = []
    title_thread = None

    if task_state.title is None:
        title_thread = concurrency_group.start_new_thread(
            target=_predict_title,
            args=(
                initial_message.text,
                title_result,
                settings,
                concurrency_group,
                root_progress_handle,
            ),
        )

    try:
        yield title_result, title_thread
    finally:
        # Ensure thread is cleaned up if still running
        if title_thread and title_thread.is_alive():
            title_thread.join()


def finalize_task_setup(
    task: Task,
    task_state: AgentTaskStateV2,
    title_thread: Thread | None,
    title_result: list[TaskTitle],
    initial_message: ChatInputUserMessage,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """Handle final task setup steps after environment is ready."""
    if title_thread is not None:
        # Resolve title prediction
        task_state = _resolve_title_prediction_thread(
            title_result=title_result,
            title_thread=title_thread,
            task_id=task.object_id,
            task_state=task_state,
            initial_message=initial_message,
            services=services,
        )

    return task_state


def _resolve_title_prediction_thread(
    title_thread: Thread,
    title_result: list[TaskTitle],
    task_id: TaskID,
    task_state: AgentTaskStateV2,
    initial_message: ChatInputUserMessage,
    services: ServiceCollectionForTask,
) -> AgentTaskStateV2:
    """
    Waits (a little while) for the title prediction thread to finish,
    then saves the title to the database.
    """
    title_thread.join(timeout=_TITLE_NAME_TIMEOUT_SECONDS)
    if title_thread.is_alive() or not title_result:
        logger.warning("Title prediction thread did not finish in time, using default")
        title = initial_message.text
    else:
        title = title_result[0].title

    # Save the title to the database, but only if the user hasn't already
    # renamed the agent (which would have set a title via the API).
    with services.data_model_service.open_task_transaction() as transaction:
        task_row = transaction.get_task(task_id)
        assert task_row is not None
        db_state = AgentTaskStateV2.model_validate(task_row.current_state)
        if db_state.title is not None:
            # User already renamed — keep their title.
            title = db_state.title

        mutable_task_state = evolver(task_state)
        assign(mutable_task_state.title, lambda: title)
        task_state = chill(mutable_task_state)

        task_row = task_row.evolve(task_row.ref().current_state, task_state.model_dump())
        _task_row = transaction.upsert_task(task_row)
    return task_state


def _predict_title(
    initial_prompt: str,
    title_result: list[TaskTitle],
    settings: SculptorSettings,
    concurrency_group: ConcurrencyGroup,
    root_progress_handle: RootProgressHandle,
) -> None:
    with start_finish_context(root_progress_handle.track_task_title_generation()) as title_generation_handler:
        if settings.TESTING.INTEGRATION_ENABLED:
            title = _generate_fixed_title_for_testing()
            title_result.append(TaskTitle(title=title))
            title_generation_handler.report_generated_title(title)
            return
        try:
            logger.debug("Generating title for task...")
            task_title = generate_title_from_prompt(initial_prompt, concurrency_group)
            logger.debug("Generated title: '{}'", task_title.title)
            title_result.append(task_title)
        except Exception as e:
            log_exception(
                e,
                "Failed to generate title",
                priority=ExceptionPriority.LOW_PRIORITY,
            )
            title = (
                initial_prompt[:_FALLBACK_TITLE_MAX_LENGTH] + "..."
                if len(initial_prompt) > _FALLBACK_TITLE_MAX_LENGTH
                else initial_prompt
            )
            logger.debug("Generated fallback title: '{}'", title)
            title_result.append(TaskTitle(title=title))
        finally:
            if title_result:
                title_generation_handler.report_generated_title(title_result[0].title)


def _generate_fixed_title_for_testing() -> str:
    global _FIXED_TITLE_COUNTER_FOR_TESTING
    _FIXED_TITLE_COUNTER_FOR_TESTING += 1
    return f"Task {_FIXED_TITLE_COUNTER_FOR_TESTING}"


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
    # That same message in full: it carries the conversation's launch settings
    # (model, fast mode, effort), which model-less turns (question answers,
    # answer-continuation resumes) continue with, so the runner re-seeds the
    # agent wrapper from it on startup.
    last_started_chat_message: ChatInputUserMessage | None
    # Every persistent message replayed in log order: user messages the agent
    # started processing plus the agent's own non-killed messages. The loop keeps
    # appending to (a copy of) this as the run produces more messages.
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage]
    # The dedup cursor: the latest settled user message in log order (None when
    # nothing is settled). _drop_already_processed_messages consumes the replayed
    # queue up to and including this id on restart.
    last_processed_message_id: AgentMessageID | None


def scan_message_history(all_messages: Sequence[Message], harness: Harness) -> HistoryScan:
    """Replay a task's persisted message log to reconstruct the loop's startup state.

    The scan is the single authority on which persisted user messages are settled
    versus still in flight after a restart: a user message is settled iff some
    ``RequestStartedAgentMessage`` references it and the scan does not leave it in
    flight. ``last_processed_message_id`` is derived from the same pass state as
    the in-flight ids, so the dedup cursor and the resume tracking cannot diverge.

    ``harness`` identifies AskUserQuestion / ExitPlanMode tool blocks in the log:
    a killed turn that is blocked on an unanswered question is settled rather
    than left in flight (see the question gate below).
    """
    persistent_user_message_by_id: dict[AgentMessageID, PersistentUserMessage] = {}
    # ids of user messages some RequestStartedAgentMessage references — i.e. user
    # messages the agent started processing at some point
    started_user_message_ids: set[AgentMessageID] = set()
    # the last user chat message that we *started* processing — tracked in case we
    # never *finished* processing it, so that the agent can resume where it left off
    last_user_chat_message_id: AgentMessageID | None = None
    last_started_chat_message: ChatInputUserMessage | None = None
    in_flight_chat_message_id: AgentMessageID | None = None
    in_flight_answer_message_id: AgentMessageID | None = None
    # Track whether the agent emitted any visible response for the in-flight chat
    # message. If it didn't, there's nothing for Claude to "resume" from — we'd
    # rather just resend the original prompt than send a "continue where you left
    # off" instruction with no prior content. Reset on each new RequestStarted.
    is_partial_agent_response = False
    # tool_use ids of AUQ / ExitPlanMode calls the user has not answered. Kept in
    # lockstep with the web layer's pending-question derivation (derived
    # ``_ready_or_waiting`` and message_conversion): a newer started user turn, a
    # settled completion, a user-initiated stop, or a context clear dismisses
    # them; a stop the user did not ask for (shutdown/restart SIGTERM) preserves
    # them, because the question is restored in the UI and stays answerable via
    # the answer-after-turn-ended continuation.
    unanswered_question_tool_use_ids: set[str] = set()
    persistent_message_history: list[PersistentUserMessage | PersistentAgentMessage] = []
    for message in all_messages:
        # just remember the last chat message from the user (that the agent started processing)
        if isinstance(message, RequestStartedAgentMessage):
            persistent_message = persistent_user_message_by_id.get(message.request_id)
            if persistent_message is not None:
                started_user_message_ids.add(message.request_id)
                if isinstance(persistent_message, ChatInputUserMessage):
                    last_user_chat_message_id = message.request_id
                    last_started_chat_message = persistent_message
                    in_flight_chat_message_id = message.request_id
                    is_partial_agent_response = False
                    # A newer user prompt began processing — it supersedes any
                    # older unanswered question.
                    unanswered_question_tool_use_ids.clear()
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
            # Any settled completion means the asking turn is over and its
            # questions can no longer be answered against it — except a stop the
            # user did not ask for, which preserves them (see the set's comment).
            if not (isinstance(message, RequestStoppedAgentMessage) and not message.stopped_by_user):
                unanswered_question_tool_use_ids.clear()
        # used above so that we can figure out which user messages started being processed so far
        if isinstance(message, PersistentUserMessage):
            persistent_user_message_by_id[message.message_id] = message
            if isinstance(message, UserQuestionAnswerMessage):
                unanswered_question_tool_use_ids.discard(message.tool_use_id)
        # remember all messages that have been emitted so far by the agent
        if isinstance(message, PersistentAgentMessage):
            was_killed = get_killed_exit_code(message)
            if not was_killed:
                persistent_message_history.append(message)
            if isinstance(message, ContextClearedMessage):
                # A cleared context wipes the session that asked — any older
                # question can no longer be answered against it.
                unanswered_question_tool_use_ids.clear()
            # A ResponseBlockAgentMessage from the in-flight turn means Claude
            # produced visible content that we'd want to continue from on resume.
            if isinstance(message, ResponseBlockAgentMessage):
                is_partial_agent_response = True
                for block in message.content:
                    if not isinstance(block, ToolUseBlock):
                        continue
                    # Invalid AUQ inputs were rejected by the MCP server, so the
                    # agent has already moved on — mirror the web layer and skip
                    # them. ExitPlanMode accepts any input per its schema.
                    if (
                        harness.is_ask_user_question_tool(block.name)
                        and harness.is_valid_ask_user_question_input(block.name, block.input)
                    ) or harness.is_exit_plan_mode_tool(block.name):
                        unanswered_question_tool_use_ids.add(block.id)
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

    # The question gate: a killed turn blocked on an unanswered question is
    # settled, not resumable. The UI restores the question and pins the task at
    # WAITING, and the user's late answer drives the continuation — so the turn
    # must not be auto-resumed here (a "continue" turn would settle or re-issue
    # the question out from under the user) nor terminalized by the orphan
    # synthesis (a turn_abandoned completion would dismiss the question in the
    # web layer's derivations).
    if unanswered_question_tool_use_ids:
        in_flight_chat_message_id = None
        dangling_chat_message_id = None

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
        last_started_chat_message=last_started_chat_message,
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
