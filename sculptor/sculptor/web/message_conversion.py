"""Converts agent messages to chat messages for the frontend."""

import datetime
from typing import Sequence

from loguru import logger

from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import AgentCrashedRunnerMessage
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskNotificationAgentMessage
from sculptor.interfaces.agents.agent import BackgroundTaskStartedAgentMessage
from sculptor.interfaces.agents.agent import ContextClearedMessage
from sculptor.interfaces.agents.agent import ContextSummaryMessage
from sculptor.interfaces.agents.agent import EnvironmentCrashedRunnerMessage
from sculptor.interfaces.agents.agent import ErrorMessage
from sculptor.interfaces.agents.agent import ErrorMessageUnion
from sculptor.interfaces.agents.agent import PartialResponseBlockAgentMessage
from sculptor.interfaces.agents.agent import PlanModeAgentMessage
from sculptor.interfaces.agents.agent import RemoveQueuedMessageAgentMessage
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StreamingMessageCompleteAgentMessage
from sculptor.interfaces.agents.agent import TurnMetricsAgentMessage
from sculptor.interfaces.agents.agent import UnexpectedErrorRunnerMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.agent import WarningAgentMessage
from sculptor.interfaces.agents.agent import WarningMessage
from sculptor.interfaces.agents.agent import WorkflowTaskProgressAgentMessage
from sculptor.interfaces.agents.artifacts import ArtifactType
from sculptor.interfaces.agents.harness import Harness
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import TaskID
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import ChatMessage
from sculptor.state.chat_state import ChatMessageRole
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import ContextClearedBlock
from sculptor.state.chat_state import ContextSummaryBlock
from sculptor.state.chat_state import ErrorBlock
from sculptor.state.chat_state import FileBlock
from sculptor.state.chat_state import ResumeResponseBlock
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.chat_state import TurnMetrics
from sculptor.state.chat_state import WarningBlock
from sculptor.state.chat_state import make_plan_approval_question
from sculptor.state.claude_state import split_text_and_media
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.state.workflow_state import WORKFLOW_TASK_TYPE
from sculptor.state.workflow_state import WorkflowTaskState
from sculptor.web.derived import SubmittedQuestionAnswers
from sculptor.web.derived import TaskUpdate

# Message type groups
ERROR_MESSAGE_TYPES = (
    EnvironmentCrashedRunnerMessage,
    UnexpectedErrorRunnerMessage,
    AgentCrashedRunnerMessage,
)

WARNING_MESSAGE_TYPES = (WarningAgentMessage,)


class _StreamingState:
    """Mutable streaming state tracked across message processing.

    Groups the variables that control how streaming partial responses are
    assembled into in-progress chat messages.  Bundling them makes it impossible
    to forget one when resetting — the previous "staircase" rendering bug was
    caused by exactly that kind of partial reset.
    """

    def __init__(self) -> None:
        self.is_active: bool = False
        self.start_index: int = 0
        self.pending_tool_results: list[ToolResultBlock] = []
        self.message_was_streamed: bool = False
        # SDK assistant_message_ids delivered via streaming partials this request.
        # Spans the whole session (only reset() clears it) so a late persistence
        # ResponseBlockAgentMessage still dedupes after UserQuestionAnswerMessage
        # reset message_was_streamed.
        self.streamed_assistant_message_ids: set[AssistantMessageID] = set()
        # first_response_message_id of the partial that built the current streaming
        # segment. A new streamed turn is detected by a CHANGE in this id between
        # partials — not by comparing against in_progress_chat_message.id, which stays
        # pinned to the FIRST turn's id and so mis-fired complete_segment on every
        # growing partial of a re-minted later turn (the "double printing"/staircase
        # bug). Preserved across complete_segment (so the next turn's first partial
        # sees the change); only reset() clears it.
        self.current_segment_first_response_id: AgentMessageID | None = None

    def reset(self) -> None:
        """Reset all streaming state to initial values.

        Must be called when a request terminates (success, failure, stop, skip)
        because StreamingMessageCompleteAgentMessage may not arrive if the agent
        was interrupted mid-stream.
        """
        self.is_active = False
        self.start_index = 0
        self.pending_tool_results = []
        self.message_was_streamed = False
        self.streamed_assistant_message_ids = set()
        self.current_segment_first_response_id = None

    def complete_segment(self, content_length: int) -> None:
        """Mark the current streaming segment as complete.

        Unlike ``reset``, this advances ``start_index`` past the committed
        content and preserves ``message_was_streamed`` so the subsequent
        persistence ``ResponseBlockAgentMessage`` still skips duplicate content.
        It also preserves ``current_segment_first_response_id`` so the next turn's
        first partial can still detect the id change at the turn boundary.
        """
        self.start_index = content_length
        self.is_active = False
        self.pending_tool_results = []


def _finalize_request(
    current_request_id: AgentMessageID | None,
    request_id: AgentMessageID,
    in_progress_chat_message: ChatMessage | None,
    completed_message_by_id: dict[AgentMessageID, ChatMessage],
    completed_chat_messages: list[ChatMessage],
) -> tuple[ChatMessage | None, AgentMessageID | None]:
    """Finalize a completed request by moving the in-progress message to completed.

    Returns the updated (in_progress_chat_message, current_request_id) pair.
    """
    if not current_request_id or request_id != current_request_id:
        return in_progress_chat_message, current_request_id

    if in_progress_chat_message:
        completed_message_by_id[in_progress_chat_message.id] = in_progress_chat_message
        completed_chat_messages.append(in_progress_chat_message)
        in_progress_chat_message = None

    return in_progress_chat_message, None


def _mark_stopped(in_progress: ChatMessage | None) -> ChatMessage | None:
    """Mark a message as stopped (user interrupted the turn).

    Returns the message unchanged when in_progress is None.
    """
    if in_progress is None:
        return None
    return in_progress.model_copy(update={"stopped": True})


def _attach_turn_metrics(in_progress: ChatMessage | None, turn_metrics: TurnMetrics | None) -> ChatMessage | None:
    """Attach per-turn metrics to a message just before it is finalized.

    Returns the message unchanged when either argument is None.
    """
    if in_progress is None or turn_metrics is None:
        return in_progress
    return in_progress.model_copy(update={"turn_metrics": turn_metrics})


def _pend_question(pending_user_questions: list[AskUserQuestionData], question_data: AskUserQuestionData) -> None:
    """Add a question to the pending queue, replacing any entry with the same
    tool_use_id (the live ephemeral message and the persisted ToolUseBlock
    reconstruction both surface the same question)."""
    for i, existing in enumerate(pending_user_questions):
        if existing.tool_use_id == question_data.tool_use_id:
            pending_user_questions[i] = question_data
            return
    pending_user_questions.append(question_data)


def _reconstruct_pending_questions_from_child_blocks(
    content: Sequence[ContentBlockTypes],
    pending_user_questions: list[AskUserQuestionData],
    submitted_question_answers: dict[str, SubmittedQuestionAnswers],
    harness: Harness,
) -> None:
    """Re-pend unanswered ask_user_question ToolUseBlocks from a SUBAGENT
    (child) message, for page-reload support. Child messages skip the main
    reconstruction loop (they `continue` out of the ResponseBlockAgentMessage
    branch), so without this a subagent's pending question would vanish on
    reload while its MCP call stays held.
    """
    for block in content:
        if not isinstance(block, ToolUseBlock) or not harness.is_ask_user_question_tool(block.name):
            continue
        if block.id in submitted_question_answers:
            continue
        reconstructed = harness.reconstruct_pending_ask_user_question(block)
        if reconstructed is not None:
            _pend_question(pending_user_questions, reconstructed)


def convert_agent_messages_to_task_update(
    new_messages: Sequence[Message | CompletedTransaction],
    task_id: TaskID,
    completed_message_by_id: dict[AgentMessageID, ChatMessage],
    harness: Harness,
    current_state: TaskUpdate | None = None,
) -> TaskUpdate:
    """Convert a batch of agent messages to a TaskUpdate.

    Takes a stream of agent messages and converts them into a TaskUpdate
    with pure UI state that can be displayed in the frontend. Manages the state
    transitions of messages from queued -> completed and builds up assistant messages
    incrementally.
    """

    completed_chat_messages = []
    queued_chat_messages = list(current_state.queued_chat_messages) if current_state else []
    in_progress_chat_message = current_state.in_progress_chat_message if current_state else None
    current_request_id = current_state.in_progress_user_message_id if current_state else None
    update_artifacts = set()
    # All currently-unanswered questions, oldest first. The frontend shows the
    # LAST entry (TaskUpdate.pending_user_question); answering it surfaces the
    # previous one. Multiple questions pend concurrently when subagents call
    # ask_user_question while another question is already waiting.
    pending_user_questions: list[AskUserQuestionData] = (
        list(current_state.pending_user_questions) if current_state else []
    )
    submitted_question_answers: dict[str, SubmittedQuestionAnswers] = (
        dict(current_state.submitted_question_answers) if current_state else {}
    )
    is_in_plan_mode: bool = current_state.is_in_plan_mode if current_state else False
    pending_turn_metrics: TurnMetrics | None = current_state.pending_turn_metrics if current_state else None
    # Background tasks whose ``task_started`` has been received but whose
    # ``task_notification`` has not. Tracked across batches so the frontend
    # can tell when the harness is sitting idle waiting on a background
    # task (SCU-387) — the parent request stays in RUNNING state during
    # that wait, so a count of pending IDs is the only signal that
    # distinguishes "agent is thinking" from "harness is idle, waiting on
    # background task completion".
    pending_background_task_ids: set[str] = set(current_state.pending_background_task_ids) if current_state else set()
    # Workflow-task state keyed by tool_use_id. Carried across batches and
    # NOT cleared at request boundaries: completed entries must stay around so
    # the workflow popover keeps rendering the final tree after the run ends.
    workflow_task_states: dict[str, WorkflowTaskState] = (
        dict(current_state.workflow_task_states) if current_state else {}
    )

    # Streaming state — groups the variables that control how partial responses
    # are assembled into in-progress chat messages.
    streaming = _StreamingState()

    # in_progress_chat_message.content[streaming.start_index:] are the content blocks that we will alter
    if current_state:
        streaming.start_index = current_state.streaming_start_index
    elif in_progress_chat_message:
        streaming.start_index = len(in_progress_chat_message.content)

    # Reconstruct pending tool results from existing content so they survive
    # partial overwrites.  Partials replace content from streaming_start_index
    # onwards, so any ToolResultBlocks in that range need to be re-applied.
    if current_state and current_state.is_streaming_active and current_state.in_progress_chat_message:
        streaming.pending_tool_results = [
            block
            for block in current_state.in_progress_chat_message.content[streaming.start_index :]
            if isinstance(block, ToolResultBlock)
        ]

    if current_state:
        streaming.is_active = current_state.is_streaming_active

    streaming.message_was_streamed = current_state.in_progress_message_was_streamed if current_state else False
    if current_state is not None:
        streaming.streamed_assistant_message_ids = set(current_state.streamed_assistant_message_ids)
        streaming.current_segment_first_response_id = current_state.streamed_segment_first_response_id

    # Track the most recent .claude/plans/* Write/Edit/MultiEdit so the
    # synthesized ExitPlanMode approval question carries plan_file_path —
    # mirrors output_processor's _recent_plan_file_path tracking on the live
    # path, but works after a backend restart / page reload too (architecture
    # §5.4).
    recent_plan_file_path: str | None = None

    for msg in new_messages:
        if isinstance(msg, ChatInputUserMessage):
            # Build content blocks from text and files
            content_blocks: list[ContentBlockTypes] = [TextBlock(text=msg.text)]
            for file in msg.files:
                content_blocks.append(FileBlock(source=file))

            # Reflect plan mode state from the user message so the frontend
            # toggle lights up immediately, before the agent processes it.
            if msg.enter_plan_mode:
                is_in_plan_mode = True
            elif msg.exit_plan_mode:
                is_in_plan_mode = False

            # Queue user message until confirmed -- unless this id is already
            # present in completed (it was promoted by a pre-shutdown
            # RequestStarted) or already queued. After a hard-kill restart the
            # resume path re-queues and re-saves the interrupted message with the
            # same object_id; re-adding it here would make the same id render as
            # both a sent message and a stuck queued message, and the duplicate
            # React key corrupts the virtualized chat list.
            is_already_completed = msg.message_id in completed_message_by_id
            is_already_queued = any(queued.id == msg.message_id for queued in queued_chat_messages)
            if not is_already_completed and not is_already_queued:
                queued_chat_messages.append(
                    ChatMessage(
                        id=msg.message_id,
                        role=ChatMessageRole.USER,
                        content=tuple(content_blocks),
                        approximate_creation_time=msg.approximate_creation_time,
                        sent_via=msg.sent_via,
                    )
                )

        elif isinstance(msg, RequestStartedAgentMessage):
            assert isinstance(msg.request_id, AgentMessageID)
            # Promote queued message to completed (if one exists for this request)
            is_promoted = False
            for i, message in enumerate(queued_chat_messages):
                if message.id == msg.request_id:
                    previously_queued_message = queued_chat_messages.pop(i)
                    completed_message_by_id[previously_queued_message.id] = previously_queued_message
                    completed_chat_messages.append(previously_queued_message)
                    is_promoted = True
                    break
            # Only update current_request_id for real content requests (matched a
            # queued message) or when idle.  Lifecycle requests like
            # RemoveQueuedMessage emit their own RequestStarted/RequestSuccess pair
            # which must not clobber the active content request's ID.
            if is_promoted or current_request_id is None:
                current_request_id = msg.request_id

        elif isinstance(msg, RemoveQueuedMessageAgentMessage):
            # Remove queued message without completing it
            queued_chat_messages = [m for m in queued_chat_messages if m.id != msg.removed_message_id]

        elif isinstance(msg, PartialResponseBlockAgentMessage):
            msg_parent = msg.parent_tool_use_id

            # Decide how this partial relates to the current in-progress message.
            #
            # Flush (start a brand-new ChatMessage) only when the subagent
            # context changed (parent_tool_use_id mismatch).
            #
            # When the partial belongs to a NEW streamed turn in the SAME agent
            # context (a fresh first_response_message_id that is not an already-
            # completed id), do NOT flush — continue the existing ChatMessage as
            # a new streaming segment. output_processor mints a fresh
            # first_response_message_id for each turn that follows a subagent
            # context switch (it updates _last_response_parent_tool_use_id on
            # interleaved subagent messages) and for each post-task_notification
            # request cycle. When concurrent subagent output interleaves between
            # the main agent's tool calls, flushing per turn fragmented the main
            # agent's tool calls into one ChatMessage each — the broken-apart
            # "staircase" rendering. Completing the segment advances the
            # streaming window so the new turn's content appends to the same
            # ChatMessage instead of overwriting the prior turn's content.
            #
            # The "not in completed" guard preserves the AUQ workaround: when a
            # partial re-uses an already-completed id (msg_2 after RequestSuccess
            # flushed msg_1(id=A) and a tool_result created in_progress(id=X)),
            # neither branch fires, so msg_2 overlays onto the tool_result
            # in_progress (keeping id=X), matching the legacy behavior.
            if in_progress_chat_message is not None:
                current_parent = in_progress_chat_message.parent_tool_use_id
                # A partial begins a NEW streamed turn when its
                # first_response_message_id differs from the id that built the
                # CURRENT segment. We compare against the tracked segment id, NOT
                # in_progress_chat_message.id: when output_processor re-mints a fresh
                # id for a turn following a subagent context switch, the in-progress
                # message keeps the FIRST turn's id forever, so comparing against it
                # stayed True for EVERY growing partial of the re-minted turn —
                # re-running complete_segment per partial and appending each snapshot
                # (the chat "double printing" / staircase of one message at growing
                # lengths). Comparing against the segment id fires complete_segment
                # once per turn; same-id continuation partials replace within it.
                starts_new_streamed_turn = (
                    streaming.current_segment_first_response_id is not None
                    and streaming.current_segment_first_response_id != msg.first_response_message_id
                    and msg.first_response_message_id not in completed_message_by_id
                )
                if msg_parent != current_parent:
                    completed_message_by_id[in_progress_chat_message.id] = in_progress_chat_message
                    completed_chat_messages.append(in_progress_chat_message)
                    in_progress_chat_message = None
                    streaming.reset()
                elif starts_new_streamed_turn:
                    streaming.complete_segment(len(in_progress_chat_message.content))

            # First partial in a turn establishes where streaming edits begin
            if not streaming.is_active:
                streaming.start_index = len(in_progress_chat_message.content) if in_progress_chat_message else 0
            streaming.is_active = True
            streaming.message_was_streamed = True
            # Remember which turn built the current segment so the NEXT partial can
            # distinguish a continuation (same id -> replace within the segment) from
            # a new turn (different id -> advance the segment once). Survives across
            # SSE batches via TaskUpdate.streamed_segment_first_response_id.
            streaming.current_segment_first_response_id = msg.first_response_message_id
            streaming.streamed_assistant_message_ids.add(msg.assistant_message_id)
            # Handle streaming partial - replace content from streaming.start_index.
            # Use first_response_message_id for the ChatMessage ID so it's stable AND persistent.
            in_progress_chat_message = _handle_partial_response(
                in_progress_chat_message,
                msg.content,
                msg.first_response_message_id,
                msg.approximate_creation_time,
                streaming.start_index,
                harness,
                parent_tool_use_id=msg_parent,
            )

            # Re-apply any tool results that arrived during streaming, since the
            # partial just overwrote them with the original ToolUseBlocks.
            for result in streaming.pending_tool_results:
                content = list(in_progress_chat_message.content)
                content, _is_replaced = _replace_tool_use_with_result(content, result, harness)
                in_progress_chat_message = in_progress_chat_message.model_copy(update={"content": tuple(content)})

        elif isinstance(msg, ResponseBlockAgentMessage):
            if streaming.is_active:
                msg_parent = msg.parent_tool_use_id
                current_parent = in_progress_chat_message.parent_tool_use_id if in_progress_chat_message else None
                if msg_parent != current_parent:
                    # Subagent message arrived during parent streaming.  Handle it
                    # as a separate completed ChatMessage so the tool blocks end up
                    # in the correct subagent context instead of leaking into the
                    # parent's in-progress message.
                    separate_msg = _handle_response_blocks(
                        None,
                        msg.content,
                        msg.message_id,
                        msg.approximate_creation_time,
                        harness,
                        parent_tool_use_id=msg_parent,
                    )
                    completed_message_by_id[separate_msg.id] = separate_msg
                    completed_chat_messages.append(separate_msg)
                    _reconstruct_pending_questions_from_child_blocks(
                        msg.content, pending_user_questions, submitted_question_answers, harness
                    )
                    continue

                # During streaming, only process tool results - text/tool_use/FileBlocks
                # are handled via partials (FileBlocks are included in streaming
                # partials by the output_processor's _build_current_content).
                non_streamed_blocks = tuple(block for block in msg.content if isinstance(block, ToolResultBlock))
                if non_streamed_blocks:
                    in_progress_chat_message = _handle_response_blocks(
                        in_progress_chat_message,
                        non_streamed_blocks,
                        msg.message_id,
                        msg.approximate_creation_time,
                        harness,
                    )
                    # Track tool results so they survive subsequent partial
                    # overwrites.  Partials replace content from
                    # streaming_start_index onwards, which would wipe
                    # ToolResultBlocks that arrived via ResponseBlockAgentMessage.
                    streaming.pending_tool_results.extend(non_streamed_blocks)
                continue
            msg_parent = msg.parent_tool_use_id

            # A subagent message (parent_tool_use_id set) that arrives between the
            # main agent's turns must NOT flush the main agent's in-progress
            # ChatMessage. Once streaming has ended (StreamingMessageComplete),
            # interleaved subagent ResponseBlocks land here rather than in the
            # streaming branch above; flushing on each one fragmented every
            # main-agent tool call interleaved with concurrent subagent output
            # into its own ChatMessage — the broken-apart "staircase" rendering.
            # Emit the subagent message as a separate completed child ChatMessage
            # instead (mirroring the streaming branch), leaving the main agent's
            # in-progress message intact so its surrounding tool calls stay
            # grouped in one ChatMessage.
            current_parent = in_progress_chat_message.parent_tool_use_id if in_progress_chat_message else None
            if msg_parent != current_parent:
                if msg_parent is not None:
                    separate_msg = _handle_response_blocks(
                        None,
                        msg.content,
                        msg.message_id,
                        msg.approximate_creation_time,
                        harness,
                        parent_tool_use_id=msg_parent,
                    )
                    completed_message_by_id[separate_msg.id] = separate_msg
                    completed_chat_messages.append(separate_msg)
                    _reconstruct_pending_questions_from_child_blocks(
                        msg.content, pending_user_questions, submitted_question_answers, harness
                    )
                    continue
                # A main-agent message (parent_tool_use_id None) arriving while a
                # different-context message is in progress — flush so the main
                # content starts in its own ChatMessage.
                if in_progress_chat_message is not None:
                    completed_message_by_id[in_progress_chat_message.id] = in_progress_chat_message
                    completed_chat_messages.append(in_progress_chat_message)
                    in_progress_chat_message = None
                    streaming.message_was_streamed = False

            # The frontend already has this message's text/tool_use content
            # if any of these holds; only ToolResultBlocks (and previously-
            # unseen FileBlocks) carry new information in that case.
            #   - we just built it via streaming partials, OR
            #   - a ChatMessage with this id was already flushed (e.g. a
            #     UserQuestionAnswerMessage flushed the in-progress before
            #     this persistence arrived, also resetting
            #     message_was_streamed to False), OR
            #   - the SDK assistant_message_id was already delivered via a
            #     streaming partial in this request.  Catches multi-step
            #     turns whose persistence gets a fresh message_id
            #     (output_processor's _used_first_response_id branch), where
            #     the prior two conditions miss because the flushed
            #     ChatMessage is keyed under first_response_message_id.
            is_already_completed = msg.message_id in completed_message_by_id
            is_assistant_already_streamed = msg.assistant_message_id in streaming.streamed_assistant_message_ids
            if streaming.message_was_streamed or is_already_completed or is_assistant_already_streamed:
                # The in-progress message was built by streaming partials.  The SDK emits
                # the full assistant message (text + tool_use blocks) as a non-streaming
                # ResponseBlockAgentMessage for DB persistence after streaming ends.
                # Its text/tool_use content is already present from partials, so we must
                # only process ToolResultBlocks and FileBlocks to avoid duplicating content.
                # FileBlocks may already be present from streaming (created by
                # _finalize_block_from_accumulator), so deduplicate by source path.
                existing_file_sources: set[str] = set()
                if in_progress_chat_message is not None:
                    existing_file_sources = {
                        block.source for block in in_progress_chat_message.content if isinstance(block, FileBlock)
                    }
                non_streamed_blocks = tuple(
                    block
                    for block in msg.content
                    if isinstance(block, ToolResultBlock)
                    or (isinstance(block, FileBlock) and block.source not in existing_file_sources)
                )
                if non_streamed_blocks:
                    in_progress_chat_message = _handle_response_blocks(
                        in_progress_chat_message,
                        non_streamed_blocks,
                        msg.message_id,
                        msg.approximate_creation_time,
                        harness,
                    )

                # SCU-512: the buffered persistence copy re-asserts the turn's
                # ToolUseBlocks.  If a tool_result arrived mid-stream it overwrote
                # its ToolUseBlock in place (``_replace_tool_use_with_result`` does
                # ``content[i] = result``), discarding the tool input.  For diff
                # tools (Edit/Write/MultiEdit) that input carries the old_string/
                # new_string the frontend needs to render the diff, so a dropped
                # ToolUseBlock leaves a bare ToolResultBlock that shows as an empty
                # pill.  Restore any ToolUseBlock the streamed copy no longer holds
                # (by id) so the pairing — and the input — survive.
                if in_progress_chat_message is not None:
                    existing_tool_use_ids = {
                        block.id for block in in_progress_chat_message.content if isinstance(block, ToolUseBlock)
                    }
                    restored_tool_uses = tuple(
                        block
                        for block in msg.content
                        if isinstance(block, ToolUseBlock) and block.id not in existing_tool_use_ids
                    )
                    if restored_tool_uses:
                        in_progress_chat_message = _restore_overwritten_tool_uses(
                            in_progress_chat_message, restored_tool_uses
                        )
            else:
                # Non-streaming (or historical replay) - append content as usual
                in_progress_chat_message = _handle_response_blocks(
                    in_progress_chat_message,
                    msg.content,
                    msg.message_id,
                    msg.approximate_creation_time,
                    harness,
                    parent_tool_use_id=msg_parent,
                )

            # Reconstruct pending_user_question from persisted ToolUseBlock for page reload support.
            # Only set it as pending if no answer has been submitted for this tool_use_id yet.
            # Strict-validate the tool_input to stay in lockstep with the MCP server's
            # validation — without this, lenient pydantic would coerce e.g.
            # ``multiSelect: 'false'`` (string) to ``False`` (bool) and re-pend a question
            # the MCP server already rejected with a JSON-RPC error, leaving the workspace
            # stuck in a yellow ``Waiting for input`` state.
            for block in msg.content:
                plan_path = harness.get_plan_file_path_from_tool_use(block)
                if plan_path is not None:
                    recent_plan_file_path = plan_path
                if isinstance(block, ToolUseBlock) and harness.is_ask_user_question_tool(block.name):
                    if block.id not in submitted_question_answers:
                        reconstructed_question = harness.reconstruct_pending_ask_user_question(block)
                        if reconstructed_question is not None:
                            _pend_question(pending_user_questions, reconstructed_question)
                        else:
                            logger.debug(
                                "Skipping AskUserQuestion pending state from persisted ToolUseBlock with invalid input: {}",
                                block.input,
                            )
                elif isinstance(block, ToolUseBlock) and harness.is_exit_plan_mode_tool(block.name):
                    if block.id not in submitted_question_answers:
                        _pend_question(
                            pending_user_questions,
                            make_plan_approval_question(block.id, plan_file_path=recent_plan_file_path),
                        )
                    # One-shot: clear so a later ExitPlanMode without a fresh
                    # plan write doesn't reuse a stale path.
                    recent_plan_file_path = None

        elif isinstance(msg, StreamingMessageCompleteAgentMessage):
            streaming.complete_segment(len(in_progress_chat_message.content) if in_progress_chat_message else 0)

        elif isinstance(msg, ResumeAgentResponseRunnerMessage):
            # add a block to indicate that we are resuming
            in_progress_chat_message = _handle_response_blocks(
                in_progress_chat_message,
                (ResumeResponseBlock(),),
                msg.message_id,
                msg.approximate_creation_time,
                harness,
            )

        elif isinstance(msg, ContextSummaryMessage):
            # Flush the in-progress message first so that the context summary
            # gets its own ChatMessage.  Without this, auto-compaction mid-turn
            # would append the block to the streaming message (sharing its ID),
            # and the resumed streaming would later overwrite it.
            if in_progress_chat_message is not None:
                completed_message_by_id[in_progress_chat_message.id] = in_progress_chat_message
                completed_chat_messages.append(in_progress_chat_message)
                in_progress_chat_message = None
                streaming.reset()
            summary_message = _add_context_summary_to_message(None, msg)
            completed_message_by_id[summary_message.id] = summary_message
            completed_chat_messages.append(summary_message)

        elif isinstance(msg, ContextClearedMessage):
            if in_progress_chat_message is not None:
                completed_message_by_id[in_progress_chat_message.id] = in_progress_chat_message
                completed_chat_messages.append(in_progress_chat_message)
                in_progress_chat_message = None
                streaming.reset()
            cleared_message = _add_context_cleared_to_message(None, msg)
            completed_message_by_id[cleared_message.id] = cleared_message
            completed_chat_messages.append(cleared_message)

        elif isinstance(msg, TurnMetricsAgentMessage):
            pending_turn_metrics = msg.turn_metrics

        elif isinstance(msg, RequestSuccessAgentMessage):
            # When the turn was interrupted before any content was streamed, there may
            # be no in-progress message yet. Create an empty one so the frontend can
            # render the "Stopped" footer — but only when this RequestSuccess is for
            # the active request (so _finalize_request will move the synthesized
            # message into completed_chat_messages on the same pass). Synthesizing
            # for a stale request_id (e.g. the lifecycle RequestSuccess of an
            # InterruptProcessUserMessage emitted after the active request was
            # already finalized) leaves the message dangling as in_progress and
            # freezes the StatusPill in a "thinking" state.
            #
            # Also skip synthesis when there's a queued user message waiting to
            # replace this turn — that's the always-interrupt-and-send / keyboard-
            # shortcut-interrupt flow where the user is moving on, not stopping.
            # Surfacing an empty "Interrupted by user" marker for the replaced
            # turn would leave a dangling assistant message between the two user
            # turns.
            can_finalize = current_request_id is not None and current_request_id == msg.request_id
            has_pending_replacement = bool(queued_chat_messages)
            if in_progress_chat_message is None and msg.interrupted and can_finalize and not has_pending_replacement:
                in_progress_chat_message = _create_empty_assistant_message(
                    chat_message_id=msg.message_id,
                    approximate_creation_time=msg.approximate_creation_time,
                )
            if msg.interrupted:
                in_progress_chat_message = _mark_stopped(in_progress_chat_message)
                # Clear any pending AUQs — the agent was interrupted so the questions
                # are no longer valid and the chat input should reappear.
                pending_user_questions.clear()
            in_progress_chat_message = _attach_turn_metrics(in_progress_chat_message, pending_turn_metrics)
            pending_turn_metrics = None
            in_progress_chat_message, current_request_id = _finalize_request(
                current_request_id,
                msg.request_id,
                in_progress_chat_message,
                completed_message_by_id,
                completed_chat_messages,
            )
            streaming.reset()
            pending_background_task_ids.clear()

        elif isinstance(msg, RequestFailureAgentMessage):
            in_progress_chat_message = _add_error_to_message(in_progress_chat_message, msg)
            # Clear any pending AUQs — the agent failed so the questions
            # are no longer valid and the chat input should reappear.
            pending_user_questions.clear()
            in_progress_chat_message, current_request_id = _finalize_request(
                current_request_id,
                msg.request_id,
                in_progress_chat_message,
                completed_message_by_id,
                completed_chat_messages,
            )
            streaming.reset()
            pending_background_task_ids.clear()

        elif isinstance(msg, RequestStoppedAgentMessage):
            # Only synthesize a stopped message when this stop is for the
            # active request. If the request_id doesn't match (e.g. a
            # UserQuestionAnswerMessage delivered mid-turn via MCP overrode
            # current_request_id, while this stop is for the original
            # ChatInputUserMessage that wrapped the whole turn),
            # _finalize_request would no-op and any synthesized message would
            # be left dangling as in_progress, freezing the StatusPill in a
            # "thinking" state until the user clicks Stop a second time.
            #
            # SCU-925: deliberately do NOT append an ErrorBlock here. A
            # RequestStoppedAgentMessage is the wrapper's SIGTERM/SIGINT
            # branch (see DefaultAgentWrapper._handle_user_message at
            # agents/default/agent_wrapper.py) — it always means the turn
            # was stopped (Sculptor restart, user Stop, etc.), not that the
            # agent crashed. The `stopped=True` marker on the chat message
            # is what tells the frontend to render the "Stopped" footer;
            # surfacing the wrapped "Agent died with exit code 143" as a red
            # error block on top of that made a normal restart look like a
            # crash to the user. Genuine crashes go through
            # RequestFailureAgentMessage and AgentCrashedRunnerMessage,
            # which still produce ErrorBlocks via the branches above and
            # below.
            can_finalize = current_request_id is not None and current_request_id == msg.request_id
            if can_finalize:
                in_progress_chat_message = _mark_stopped(in_progress_chat_message)
                in_progress_chat_message = _attach_turn_metrics(in_progress_chat_message, pending_turn_metrics)
                pending_turn_metrics = None
                # Clear any pending AUQs — the turn was stopped so the
                # questions are no longer answerable and the chat input
                # should reappear.
                pending_user_questions.clear()
            in_progress_chat_message, current_request_id = _finalize_request(
                current_request_id,
                msg.request_id,
                in_progress_chat_message,
                completed_message_by_id,
                completed_chat_messages,
            )
            streaming.reset()
            pending_background_task_ids.clear()

        elif isinstance(msg, RequestSkippedAgentMessage):
            in_progress_chat_message, current_request_id = _finalize_request(
                current_request_id,
                msg.request_id,
                in_progress_chat_message,
                completed_message_by_id,
                completed_chat_messages,
            )
            streaming.reset()
            pending_background_task_ids.clear()

        elif isinstance(msg, ERROR_MESSAGE_TYPES):
            # Add error block to assistant message
            if in_progress_chat_message is not None:
                in_progress_chat_message = _add_error_to_message(in_progress_chat_message, msg)
            else:
                new_message = _add_error_to_message(in_progress_chat_message, msg)
                completed_message_by_id[new_message.id] = new_message
                completed_chat_messages.append(new_message)

        elif isinstance(msg, WARNING_MESSAGE_TYPES):
            # Add warning block to assistant message
            if in_progress_chat_message is not None:
                in_progress_chat_message = _add_warning_to_message(in_progress_chat_message, msg)
            else:
                new_message = _add_warning_to_message(in_progress_chat_message, msg)
                completed_message_by_id[new_message.id] = new_message
                completed_chat_messages.append(new_message)

        elif isinstance(msg, BackgroundTaskStartedAgentMessage):
            # Record the in-flight background task so the frontend can
            # distinguish "agent is thinking" from "harness is idle, waiting
            # on a task_notification" (SCU-387). The matching discard fires
            # in BackgroundTaskNotificationAgentMessage below.
            pending_background_task_ids.add(msg.background_task_id)
            # Seed a running workflow entry at launch so the Workflow pill
            # reflects the run before the first progress tick arrives.
            if msg.task_type == WORKFLOW_TASK_TYPE:
                workflow_task_states[msg.tool_use_id] = WorkflowTaskState(
                    task_id=msg.background_task_id,
                    tool_use_id=msg.tool_use_id,
                    workflow_name=msg.workflow_name,
                    status="running",
                )

        elif isinstance(msg, WorkflowTaskProgressAgentMessage):
            # Sticky fields carry forward through ticks that omit them: a
            # tree-only delta has no last_tool_name/summary and must not blank
            # values a previous tick established.
            previous_state = workflow_task_states.get(msg.tool_use_id)
            workflow_task_states[msg.tool_use_id] = WorkflowTaskState(
                task_id=msg.background_task_id,
                tool_use_id=msg.tool_use_id,
                workflow_name=msg.workflow_name or (previous_state.workflow_name if previous_state else ""),
                status="running",
                entries=msg.entries,
                usage=msg.usage or (previous_state.usage if previous_state else None),
                last_tool_name=msg.last_tool_name or (previous_state.last_tool_name if previous_state else None),
                summary=msg.summary or (previous_state.summary if previous_state else ""),
            )

        elif isinstance(msg, BackgroundTaskNotificationAgentMessage):
            pending_background_task_ids.discard(msg.background_task_id)
            # Flip the workflow entry to its final status. The
            # ``final_workflow_entries is not None`` condition rebuilds the
            # entry from history replay (a fresh connection never sees the
            # ephemeral progress/started messages, only this persisted
            # notification) — workflow notifications always carry a tuple,
            # empty when the run reported no tree before finishing.
            if msg.tool_use_id in workflow_task_states or msg.final_workflow_entries is not None:
                previous_state = workflow_task_states.get(msg.tool_use_id)
                workflow_task_states[msg.tool_use_id] = WorkflowTaskState(
                    task_id=msg.background_task_id,
                    tool_use_id=msg.tool_use_id,
                    workflow_name=msg.workflow_name or (previous_state.workflow_name if previous_state else ""),
                    status=msg.status or "completed",
                    entries=msg.final_workflow_entries
                    if msg.final_workflow_entries is not None
                    else (previous_state.entries if previous_state else ()),
                    usage=msg.workflow_usage or (previous_state.usage if previous_state else None),
                    summary=msg.summary,
                )
                # Workflow completions must never synthesize a subagent child.
                # The tool-name fallback below cannot be relied on here: in
                # streamed turns the Workflow ToolUseBlock is result-replaced
                # in the finalized message, so _find_tool_use_by_id comes up
                # empty and the fallback would attach a child — which makes
                # AlphaToolGroup misclassify the Workflow call as a subagent
                # (children.length > 0) and drop the pill. The pill's
                # completion signal is the status flip in workflow_task_states
                # above, not a child message.
                continue
            # A background task completed. The notification is an out-of-band
            # signal that does not itself end the current request cycle, so we
            # do NOT flush the in-progress message here.  Message boundaries are
            # established naturally by RequestSuccess (end of turn) or by a
            # parent_tool_use_id change (subagent context switch).
            #
            # Flushing on notification would break the mid-turn case: when the
            # notification arrives between tool-call batches in the same turn,
            # the subsequent batch gets a fresh in-progress message reusing the
            # same first_response_message_id. The frontend dedupes by id,
            # silently dropping the pre-notification content.
            #
            # We DO, however, synthesize a child ChatMessage attached to the
            # Agent ToolUseBlock (matched via parent_tool_use_id=msg.tool_use_id).
            # Real Claude (the Agent-tool background-task path) routes the
            # subagent's content through a separate CLI process — only this
            # notification and the launch-ack ever reach the parent's stream.
            # buildSubagentMetadataMap's second pass treats child messages as
            # the completion signal for background subagents; without a
            # synthetic message here, the pill's `isThinking` stays true
            # forever and the timer ticks up indefinitely.  See SCU-1151.
            #
            # Skip the synthesis when the parent tool is identifiable and is
            # NOT Agent/Task — the same notification subtype also fires for
            # ``run_in_background`` (and auto-promoted ``local_bash``) Bash
            # calls, and a child ChatMessage attached to a Bash tool_use_id
            # causes AlphaToolGroup to misclassify the Bash as a subagent
            # (children.length > 0) and render a subagent pill instead of the
            # bash block — the bash command appears to vanish.
            #
            # The lookup MUST span the whole conversation history, not just the
            # messages completed in this batch: a background task's notification
            # routinely arrives in a SEPARATE conversion batch from the one that
            # finalized the launching turn (e.g. the user Stops the turn, the
            # detached command keeps running, and its completion is delivered on
            # the next invocation). By then the parent Bash ToolUseBlock lives
            # only in ``completed_message_by_id``. Searching only the per-batch
            # list there would miss it, fall through, and synthesize the
            # subagent-misrendering child. We only synthesize when the parent is
            # genuinely unknown (a notification for a tool we never saw) or is
            # Agent/Task (where the child IS the completion signal — see SCU-1151).
            #
            # When the CLI's `usage.duration_ms` is available we backdate the
            # synthetic message's timestamp to (parent + duration_seconds) so
            # the displayed duration is exact; otherwise we fall back to the
            # notification's arrival time, which is close to the real run
            # time but pays a few hundred ms of overhead.
            parent_tool_use = _find_tool_use_by_id(
                msg.tool_use_id,
                in_progress_chat_message,
                completed_message_by_id,
            )
            if parent_tool_use is not None and parent_tool_use[0].name not in ("Agent", "Task"):
                continue
            synthetic_creation_time = msg.approximate_creation_time
            duration_seconds = msg.duration_seconds
            if duration_seconds is not None and parent_tool_use is not None:
                synthetic_creation_time = parent_tool_use[1] + datetime.timedelta(seconds=duration_seconds)
            synthetic = ChatMessage(
                id=msg.message_id,
                role=ChatMessageRole.ASSISTANT,
                content=(TextBlock(text=msg.summary),),
                parent_tool_use_id=msg.tool_use_id,
                approximate_creation_time=synthetic_creation_time,
            )
            completed_message_by_id[synthetic.id] = synthetic
            completed_chat_messages.append(synthetic)

        elif isinstance(msg, UpdatedArtifactAgentMessage):
            artifact_type = ArtifactType(msg.artifact.name)
            if artifact_type:
                update_artifacts.add(artifact_type)

        elif isinstance(msg, AskUserQuestionAgentMessage):
            if msg.question_data.tool_use_id not in submitted_question_answers:
                _pend_question(pending_user_questions, msg.question_data)

        elif isinstance(msg, PlanModeAgentMessage):
            is_in_plan_mode = msg.is_in_plan_mode

        elif isinstance(msg, UserQuestionAnswerMessage):
            # Flush the in-progress assistant message before starting the answer's request.
            # When UserQuestionAnswerMessage arrives before RequestSuccessAgentMessage from
            # the preceding agent invocation (a race between the HTTP answer endpoint and the
            # agent output queue), the in-progress message would stay open and subsequent
            # response blocks from the follow-up invocation would be appended to it, merging
            # two assistant messages into one.
            #
            # Safety: The in-progress message is always content-complete by this point.
            # The user can only submit an answer after seeing the AskUserQuestion in the UI,
            # which requires the agent to have already emitted all content and exited. The
            # only thing still in-flight is the bookkeeping RequestSuccessAgentMessage.
            if in_progress_chat_message is not None:
                completed_message_by_id[in_progress_chat_message.id] = in_progress_chat_message
                completed_chat_messages.append(in_progress_chat_message)
                in_progress_chat_message = None
                streaming.message_was_streamed = False

            # Retire only the answered question; any other still-unanswered
            # question (e.g. a second concurrent subagent question) surfaces
            # next via the queue's new last entry.
            pending_user_questions[:] = [q for q in pending_user_questions if q.tool_use_id != msg.tool_use_id]
            current_request_id = msg.message_id
            submitted_question_answers[msg.tool_use_id] = SubmittedQuestionAnswers(
                question_data=msg.question_data,
                answers=msg.answers,
                tool_use_id=msg.tool_use_id,
            )

    # Build final update
    return TaskUpdate(
        task_id=task_id,
        chat_messages=tuple(completed_chat_messages),
        in_progress_chat_message=in_progress_chat_message,
        queued_chat_messages=tuple(queued_chat_messages),
        updated_artifacts=tuple(update_artifacts),
        in_progress_user_message_id=current_request_id,
        streaming_start_index=streaming.start_index,
        is_streaming_active=streaming.is_active,
        in_progress_message_was_streamed=streaming.message_was_streamed,
        streamed_assistant_message_ids=frozenset(streaming.streamed_assistant_message_ids),
        streamed_segment_first_response_id=streaming.current_segment_first_response_id,
        pending_user_question=pending_user_questions[-1] if pending_user_questions else None,
        pending_user_questions=tuple(pending_user_questions),
        submitted_question_answers=submitted_question_answers,
        is_in_plan_mode=is_in_plan_mode,
        pending_turn_metrics=pending_turn_metrics,
        pending_background_task_ids=frozenset(pending_background_task_ids),
        workflow_task_states=workflow_task_states,
    )


def _find_tool_use_by_id(
    tool_use_id: str,
    in_progress: ChatMessage | None,
    completed_message_by_id: dict[AgentMessageID, ChatMessage],
) -> tuple[ToolUseBlock, datetime.datetime] | None:
    """Locate a ToolUseBlock by id and return it alongside the
    approximate_creation_time of the ChatMessage that contains it.

    Returns ``None`` when no matching block is known. Used by
    BackgroundTaskNotificationAgentMessage handling to (a) decide whether to
    synthesize a completion child (only for Agent/Task tools — see SCU-1151)
    and (b) timestamp that child as (parent + duration_seconds) so the
    subagent pill shows the exact wallclock duration rather than the
    notification's arrival delay.

    Searches ``completed_message_by_id`` — the full conversation history that
    persists across conversion batches — NOT just the messages completed in the
    current batch. A background task's ``task_notification`` routinely lands in a
    later batch, after its launching turn was already finalized and flushed to
    history, so the parent ToolUseBlock is no longer in the current batch. Missing
    it there would let the caller synthesize a child on a background Bash's
    tool_use_id, which makes the frontend misrender the Bash as a subagent pill so
    the bash block vanishes once the turn is done.
    """
    candidates: list[ChatMessage] = []
    if in_progress is not None:
        candidates.append(in_progress)
    candidates.extend(completed_message_by_id.values())
    for chat_message in candidates:
        for block in chat_message.content:
            if isinstance(block, ToolUseBlock) and block.id == tool_use_id:
                return block, chat_message.approximate_creation_time
    return None


def _create_empty_assistant_message(
    chat_message_id: AgentMessageID,
    approximate_creation_time: datetime.datetime,
    parent_tool_use_id: str | None = None,
) -> ChatMessage:
    """Create a new empty assistant message."""
    return ChatMessage(
        id=chat_message_id,
        role=ChatMessageRole.ASSISTANT,
        content=(),
        parent_tool_use_id=parent_tool_use_id,
        approximate_creation_time=approximate_creation_time,
    )


def _stamp_interactive_role(block: ContentBlockTypes, harness: Harness) -> ContentBlockTypes:
    """Stamp a tool block with its harness-derived interactive-backchannel role.

    Applied wherever tool blocks enter the converted content — the final
    (`_handle_response_blocks`) AND the streaming-partial (`_handle_partial_response`)
    paths — so the frontend renders ask-user-question / plan-approval tools by
    role rather than by tool name, whichever path delivered the block first.
    Non-tool blocks pass through unchanged.
    """
    if isinstance(block, ToolUseBlock):
        return block.model_copy(update={"interactive_role": harness.classify_tool_ui_role(block.name)})
    if isinstance(block, ToolResultBlock):
        return block.model_copy(update={"interactive_role": harness.classify_tool_ui_role(block.tool_name)})
    return block


def _handle_response_blocks(
    in_progress: ChatMessage | None,
    blocks: tuple[ContentBlockTypes, ...],
    agent_message_id: AgentMessageID,
    approximate_creation_time: datetime.datetime,
    harness: Harness,
    parent_tool_use_id: str | None = None,
) -> ChatMessage:
    """Process response blocks, returns the updated in-progress chat message.

    Handles both text/tool use blocks (append) and tool result blocks
    (replace matching tool use or append if no match).
    """
    if not in_progress:
        in_progress = _create_empty_assistant_message(
            chat_message_id=agent_message_id,
            approximate_creation_time=approximate_creation_time,
            parent_tool_use_id=parent_tool_use_id,
        )

    content = list(in_progress.content)

    existing_tool_use_ids = {b.id for b in content if isinstance(b, ToolUseBlock)}

    # Process blocks in two passes to ensure ToolUseBlocks exist before we try to replace them
    # with ToolResultBlocks. This matters when loading persisted messages where all blocks
    # arrive in a single ResponseBlockAgentMessage, potentially in any order.
    tool_result_blocks: list[ToolResultBlock] = []

    # First pass: Process TextBlocks, FileBlocks, and ToolUseBlocks
    for block in blocks:
        if isinstance(block, TextBlock):
            # Extract <img>/<video> tags from text and create interleaved
            # TextBlock/FileBlock segments.  During streaming this is done by
            # the output_processor, but persisted messages still contain the
            # raw tags which must be extracted here so images survive a
            # restart/replay.
            content.extend(split_text_and_media(block.text))
        elif isinstance(block, FileBlock):
            content.append(block)
        elif isinstance(block, ToolUseBlock):
            # Skip duplicate ToolUseBlocks (e.g. from streaming persistence arriving
            # after StreamingMessageComplete).
            if block.id not in existing_tool_use_ids:
                # For AskUserQuestion, remove any existing ToolResultBlock with matching tool_use_id.
                # This handles the case where ToolResultBlock arrived in a previous message
                # before ToolUseBlock (which can happen during streaming or persistence).
                if harness.classify_tool_ui_role(block.name) is not None:
                    content = [
                        b for b in content if not (isinstance(b, ToolResultBlock) and b.tool_use_id == block.id)
                    ]

                # Stamp the harness-derived interactive role so the frontend
                # renders backchannel tools by role rather than by tool name.
                content.append(_stamp_interactive_role(block, harness))
                existing_tool_use_ids.add(block.id)
        elif isinstance(block, ToolResultBlock):
            # Defer ToolResultBlocks to second pass
            tool_result_blocks.append(block)

    # Second pass: Process ToolResultBlocks now that all ToolUseBlocks are in place
    for block in tool_result_blocks:
        # Stamp the harness-derived role so a backchannel result that survives to
        # the frontend (its tool use lived in an earlier message) is suppressed by
        # role rather than by tool name. Stamped inline (not via
        # `_stamp_interactive_role`) to keep the narrow `ToolResultBlock` type
        # `_replace_tool_use_with_result` requires.
        block = block.model_copy(update={"interactive_role": harness.classify_tool_ui_role(block.tool_name)})
        # Try to replace matching tool use with result
        content, is_replaced = _replace_tool_use_with_result(content, block, harness)

        if not is_replaced:
            content.append(block)

    return in_progress.model_copy(update={"content": tuple(content)})


def _replace_tool_use_with_result(
    content: list[ContentBlockTypes], result: ToolResultBlock, harness: Harness
) -> tuple[list[ContentBlockTypes], bool]:
    """Try to replace a tool use block with its result.

    Returns (updated_content, was_replaced).
    """
    for i, block in enumerate(content):
        if isinstance(block, ToolUseBlock) and block.id == result.tool_use_id:
            # Don't replace AskUserQuestion tool_use blocks with their tool_result.
            # The ToolUseBlock must remain so the frontend renders the custom
            # AskUserQuestionToolBlock component (which checks type === "tool_use").
            if harness.is_ask_user_question_tool(block.name) or harness.is_exit_plan_mode_tool(block.name):
                return content, True
            # Don't replace Agent/Task tool_use blocks. The frontend needs the
            # ToolUseBlock to render the subagent pill/block. For background
            # subagents, the tool_result arrives immediately ("Async agent
            # launched") and would erase the ToolUseBlock before subagent child
            # messages arrive — breaking the subagent tree. Insert the result
            # after the tool_use so the frontend can extract metadata from it.
            if block.name in ("Agent", "Task"):
                already_has_result = any(
                    isinstance(b, ToolResultBlock) and b.tool_use_id == result.tool_use_id for b in content
                )
                if not already_has_result:
                    content.insert(i + 1, result)
                return content, True
            content[i] = result
            return content, True
    return content, False


def _restore_overwritten_tool_uses(
    in_progress: ChatMessage,
    tool_uses: Sequence[ToolUseBlock],
) -> ChatMessage:
    """Re-insert ToolUseBlocks that a mid-stream tool_result overwrote in place.

    SCU-512: while streaming, ``_replace_tool_use_with_result`` swaps a
    ToolUseBlock for its ToolResultBlock (``content[i] = result``), which drops
    the tool input.  For diff tools that input is the only source of the diff the
    frontend renders.  When the buffered persistence message later re-asserts the
    ToolUseBlock, this restores it: each tool_use is inserted immediately before
    its matching ToolResultBlock (paired by ``tool_use_id``) so the frontend
    renders the pair; if no matching result is present it is appended.
    """
    content = list(in_progress.content)
    for tool_use in tool_uses:
        insert_at = next(
            (
                i
                for i, block in enumerate(content)
                if isinstance(block, ToolResultBlock) and block.tool_use_id == tool_use.id
            ),
            None,
        )
        if insert_at is None:
            content.append(tool_use)
        else:
            content.insert(insert_at, tool_use)
    return in_progress.model_copy(update={"content": tuple(content)})


def _handle_partial_response(
    in_progress: ChatMessage | None,
    content: tuple[ContentBlockTypes, ...],
    message_id: AgentMessageID,
    approximate_creation_time: datetime.datetime,
    streaming_start_index: int,
    harness: Harness,
    parent_tool_use_id: str | None = None,
) -> ChatMessage:
    """Handle streaming partial - replace content from streaming_start_index."""
    if not in_progress:
        in_progress = _create_empty_assistant_message(
            chat_message_id=message_id,
            approximate_creation_time=approximate_creation_time,
            parent_tool_use_id=parent_tool_use_id,
        )

    # Replace content from streaming_start_index onwards
    committed_content = in_progress.content[:streaming_start_index]

    # Skip ToolUseBlocks whose ID already exists in the committed content to prevent
    # duplication (e.g. if persistence ResponseBlockAgentMessage arrived before the partial).
    # Stamp the interactive role here too: a backchannel tool's block is delivered
    # via the partial first, and the later final ResponseBlockAgentMessage skips it
    # as a duplicate — so without stamping on this path the live turn never gets a role.
    committed_tool_use_ids = {b.id for b in committed_content if isinstance(b, ToolUseBlock)}
    deduplicated = tuple(
        _stamp_interactive_role(b, harness)
        for b in content
        if not (isinstance(b, ToolUseBlock) and b.id in committed_tool_use_ids)
    )
    new_content = committed_content + deduplicated

    return in_progress.model_copy(update={"content": new_content})


def _add_context_summary_to_message(
    in_progress: ChatMessage | None,
    message: ContextSummaryMessage,
) -> ChatMessage:
    """Add a context summary block to the message."""
    # although all elements of `ContextSummaryMessage` are `Message`s, keep the runtime assert as a defensive guard
    assert isinstance(message, Message)

    context_summary_block = ContextSummaryBlock(
        text=message.content,
    )

    return _add_system_block_to_message(
        in_progress,
        context_summary_block,
        chat_message_id=message.message_id,
        approximate_creation_time=message.approximate_creation_time,
    )


def _add_context_cleared_to_message(
    in_progress: ChatMessage | None,
    message: ContextClearedMessage,
) -> ChatMessage:
    """Add context cleared block to message."""
    assert isinstance(message, Message)

    context_cleared_block = ContextClearedBlock()

    return _add_system_block_to_message(
        in_progress,
        context_cleared_block,
        chat_message_id=message.message_id,
        approximate_creation_time=message.approximate_creation_time,
    )


def _add_error_to_message(
    in_progress: ChatMessage | None,
    message: ErrorMessageUnion,
) -> ChatMessage:
    """Add error block to message."""
    # although all elements of `ErrorMessageUnion` are `ErrorMessage`s, keep the runtime assert as a defensive guard
    assert isinstance(message, ErrorMessage)
    error = message.error
    chat_message_id = message.message_id
    if not isinstance(error, SerializedException):
        logger.error("Expected SerializedException, got {}", type(message.error))
        return in_progress or _create_empty_assistant_message(
            chat_message_id=chat_message_id,
            approximate_creation_time=message.approximate_creation_time,
        )

    args = message.error.args
    message_text = args[0] if args and isinstance(args[0], str) else f"{message.error}"
    error_block = ErrorBlock(
        message=message_text,
        traceback=message.error.as_formatted_traceback(),
        error_type=message.error.exception,
    )

    return _add_system_block_to_message(
        in_progress=in_progress,
        block=error_block,
        chat_message_id=chat_message_id,
        approximate_creation_time=message.approximate_creation_time,
    )


def _add_warning_to_message(in_progress: ChatMessage | None, message: WarningMessage) -> ChatMessage:
    """Add warning block to message."""
    traceback = None
    warning_type = None

    # although WarningMessage is a Message, keep the runtime assert as a defensive guard
    assert isinstance(message, Message)
    error = message.error

    if isinstance(error, SerializedException):
        traceback = error.as_formatted_traceback()
        warning_type = error.exception

    warning_block = WarningBlock(
        message=message.message,
        traceback=traceback,
        warning_type=warning_type,
    )

    return _add_system_block_to_message(
        in_progress=in_progress,
        block=warning_block,
        chat_message_id=message.message_id,
        approximate_creation_time=message.approximate_creation_time,
    )


def _add_system_block_to_message(
    in_progress: ChatMessage | None,
    block: ContentBlockTypes,
    chat_message_id: AgentMessageID,
    approximate_creation_time: datetime.datetime,
) -> ChatMessage:
    """Add any system block (error/warning) to message."""
    if not in_progress:
        in_progress = _create_empty_assistant_message(
            chat_message_id=chat_message_id,
            approximate_creation_time=approximate_creation_time,
        )

    return in_progress.model_copy(update={"content": in_progress.content + (block,)})
