// Builds a wire `TaskUpdate` from the fold state.
//
// The Python projection (`_apply_message_updates_to_task_state` +
// `convert_agent_messages_to_task_update`) keeps a per-task `TaskUpdate` whose
// fields it carries across SSE batches. In the rewrite the warm cache holds the
// equivalent `FoldState`; this module projects that fold state into the wire
// `TaskUpdate` shape so the snapshot and the agent_message delta emit the same
// object.
//
// For a snapshot the whole current state is sent (all completed messages, the
// in-progress message, the queue). Incremental deltas reuse the same builder —
// the frontend's append/replace merge semantics make a full per-task TaskUpdate
// idempotent for the keys it carries.

import type { FoldState } from "~/projection/message_conversion";
import type { TaskUpdate } from "~/projection/streaming_update_types";

export function foldStateToTaskUpdate(taskId: string, state: FoldState): TaskUpdate {
  const streaming = state.streaming;
  return {
    task_id: taskId,
    chat_messages: [...state.completedChatMessages],
    updated_artifacts: [...state.updatedArtifacts],
    in_progress_chat_message: state.inProgressChatMessage,
    queued_chat_messages: [...state.queuedChatMessages],
    // The id of the user message whose request is currently in flight (the
    // "working" turn). The frontend's status pill needs it to show "Thinking…"
    // while a RUNNING agent has produced no streamed content yet
    // (in_progress_user_message_id = current_request_id).
    in_progress_user_message_id: state.currentRequestId,
    streaming_start_index: streaming.startIndex,
    is_streaming_active: streaming.isActive,
    in_progress_message_was_streamed: streaming.messageWasStreamed,
    streamed_assistant_message_ids: [...streaming.streamedAssistantMessageIds],
    streamed_segment_first_response_id: streaming.currentSegmentFirstResponseId,
    pending_user_question: state.pendingUserQuestion,
    // Answered AUQ/plan questions, keyed by tool_use_id, so the frontend renders
    // the answered tool block in history (the question + the user's selection).
    submitted_question_answers: Object.fromEntries(state.submittedQuestionAnswers),
    is_in_plan_mode: state.isInPlanMode,
    pending_turn_metrics: state.pendingTurnMetrics,
    pending_background_task_ids: [...state.pendingBackgroundTaskIds],
  };
}
