import type { StreamingUpdate } from "~/projection/streaming_update_types";

// Wire serialization for the StreamingUpdate projection.
//
// The projection is snake_case internally end-to-end (the harness writes
// snake-case message blocks, the fold passes them through, the warm cache holds
// them, the golden fixtures pin them). Python keeps the same snake_case internal
// models and camelCases ONLY at the WS send boundary via
// `model_dump(mode="json", by_alias=True)` (app.py `_get_next_elem_for_websocket`).
// This module is that boundary: it converts the internal snake_case
// StreamingUpdate to the camelCase wire shape the frontend reads,
// field-aware so it preserves the three things `to_camel` must NOT touch:
//   1. entity-id MAP KEYS (the `*ByTaskId` / `*ByWorkspaceId` dicts are keyed by
//      ids like `tsk_…` / `ws_…` — data, not field names).
//   2. opaque tool payloads (ToolUseBlock.input, SimpleToolContent.tool_input /
//      tool_content) — raw tool args the frontend renders verbatim.
//   3. SculptorSettings (`user_update.settings`) — not a to_camel model; its keys
//      stay as-is (UPPERCASE). A lowercase-only camelizer leaves them untouched.

type Json = Record<string, unknown>;

// Pydantic's alias_generator=to_camel: snake_case -> camelCase. Lowercase-only,
// so UPPERCASE keys (SculptorSettings) and id-like tokens are unaffected.
function toCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_match, char: string) =>
    char.toUpperCase(),
  );
}

// Recursively camelize object KEYS. Safe ONLY for subtrees with no opaque
// payloads and no data-keyed maps (the model-field-only structures below).
export function camelizeDeep(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(camelizeDeep);
  }
  if (value !== null && typeof value === "object") {
    const out: Json = {};
    for (const [key, inner] of Object.entries(value)) {
      out[toCamel(key)] = camelizeDeep(inner);
    }
    return out;
  }
  return value;
}

// Map a `dict[id, X]` to the wire, preserving the (data) keys and converting
// each value. Null values (deleted-entity markers) pass through.
function mapValues<T>(
  map: Record<string, T>,
  convert: (value: T) => unknown,
): Json {
  const out: Json = {};
  for (const [key, value] of Object.entries(map)) {
    out[key] = value === null ? null : convert(value);
  }
  return out;
}

// Tool result content. `simple` carries opaque tool_input / tool_content that
// must pass through verbatim; `diff` / `generic` are plain model fields.
function toolContentToWire(content: Json): Json {
  switch (content.content_type) {
    case "diff":
      return {
        contentType: "diff",
        diff: content.diff,
        filePath: content.file_path,
      };
    case "simple":
      return {
        contentType: "simple",
        text: content.text,
        toolInput: content.tool_input,
        toolContent: content.tool_content,
      };
    default:
      return { contentType: content.content_type, text: content.text };
  }
}

function blockToWire(block: Json): Json {
  switch (block.object_type) {
    case "ToolUseBlock":
      return {
        objectType: "ToolUseBlock",
        type: block.type,
        id: block.id,
        name: block.name,
        input: block.input, // opaque tool args — verbatim
        interactiveRole: block.interactive_role,
      };
    case "ToolResultBlock":
      return {
        objectType: "ToolResultBlock",
        type: block.type,
        toolUseId: block.tool_use_id,
        toolName: block.tool_name,
        invocationString: block.invocation_string,
        content: toolContentToWire(block.content as Json),
        isError: block.is_error,
        durationSeconds: block.duration_seconds,
        interactiveRole: block.interactive_role,
        description: block.description,
      };
    case "ToolResultBlockSimple":
      return {
        objectType: "ToolResultBlockSimple",
        type: block.type,
        toolUseId: block.tool_use_id,
        toolName: block.tool_name,
        invocationString: block.invocation_string,
        content: toolContentToWire(block.content as Json),
        isError: block.is_error,
        durationSeconds: block.duration_seconds,
        description: block.description,
      };
    case "WarningBlock":
      return {
        objectType: "WarningBlock",
        type: block.type,
        message: block.message,
        traceback: block.traceback,
        warningType: block.warning_type,
      };
    case "ErrorBlock":
      return {
        objectType: "ErrorBlock",
        type: block.type,
        message: block.message,
        traceback: block.traceback,
        errorType: block.error_type,
      };
    default:
      // TextBlock / ContextSummaryBlock / ContextClearedBlock /
      // ResumeResponseBlock / FileBlock — only plain snake model fields.
      return camelizeDeep(block) as Json;
  }
}

function chatMessageToWire(message: Json): Json {
  const content = Array.isArray(message.content)
    ? (message.content as Json[])
    : [];
  return {
    role: message.role,
    id: message.id,
    content: content.map(blockToWire),
    parentToolUseId: message.parent_tool_use_id,
    approximateCreationTime: message.approximate_creation_time,
    turnMetrics:
      message.turn_metrics === null ? null : camelizeDeep(message.turn_metrics),
    stopped: message.stopped,
    sentVia: message.sent_via,
  };
}

function nullableMessage(message: unknown): unknown {
  return message === null || message === undefined
    ? null
    : chatMessageToWire(message as Json);
}

// SubmittedQuestionAnswers: outer keys are tool_use_ids (data, preserved by
// mapValues); `answers` is keyed by question header (data) so it passes through.
function submittedAnswersToWire(value: Json): Json {
  return {
    questionData: camelizeDeep(value.question_data),
    answers: value.answers,
    toolUseId: value.tool_use_id,
  };
}

function taskUpdateToWire(update: Json): Json {
  return {
    taskId: update.task_id,
    chatMessages: (update.chat_messages as Json[]).map(chatMessageToWire),
    updatedArtifacts: update.updated_artifacts,
    inProgressChatMessage: nullableMessage(update.in_progress_chat_message),
    queuedChatMessages: (update.queued_chat_messages as Json[]).map(
      chatMessageToWire,
    ),
    inProgressUserMessageId: update.in_progress_user_message_id,
    streamingStartIndex: update.streaming_start_index,
    isStreamingActive: update.is_streaming_active,
    inProgressMessageWasStreamed: update.in_progress_message_was_streamed,
    streamedAssistantMessageIds: update.streamed_assistant_message_ids,
    streamedSegmentFirstResponseId: update.streamed_segment_first_response_id,
    pendingUserQuestion:
      update.pending_user_question === null
        ? null
        : camelizeDeep(update.pending_user_question),
    submittedQuestionAnswers: mapValues(
      update.submitted_question_answers as Record<string, Json>,
      submittedAnswersToWire,
    ),
    isInPlanMode: update.is_in_plan_mode,
    pendingTurnMetrics:
      update.pending_turn_metrics === null
        ? null
        : camelizeDeep(update.pending_turn_metrics),
    pendingBackgroundTaskIds: update.pending_background_task_ids,
  };
}

function userUpdateToWire(userUpdate: Json): Json {
  return {
    userSettings:
      userUpdate.user_settings === null
        ? null
        : camelizeDeep(userUpdate.user_settings),
    projects: (userUpdate.projects as Json[]).map(camelizeDeep),
    workspaces: (userUpdate.workspaces as Json[]).map(camelizeDeep),
    // SculptorSettings is opaque and NOT a to_camel model — verbatim.
    settings: userUpdate.settings,
    notifications: (userUpdate.notifications as Json[]).map(camelizeDeep),
  };
}

function arrayValue(value: unknown[]): unknown {
  return value.map(camelizeDeep);
}

// Convert an internal (snake_case) StreamingUpdate to its camelCase wire shape.
export function streamingUpdateToWire(update: StreamingUpdate): Json {
  return {
    taskUpdateByTaskId: mapValues(
      update.task_update_by_task_id as unknown as Record<string, Json>,
      taskUpdateToWire,
    ),
    taskViewsByTaskId: mapValues(
      update.task_views_by_task_id as unknown as Record<string, Json>,
      camelizeDeep,
    ),
    userUpdate: userUpdateToWire(update.user_update as unknown as Json),
    workspaceBranchByWorkspaceId: mapValues(
      update.workspace_branch_by_workspace_id as unknown as Record<
        string,
        Json
      >,
      camelizeDeep,
    ),
    workspaceRemoteBranchesByWorkspaceId: mapValues(
      update.workspace_remote_branches_by_workspace_id as unknown as Record<
        string,
        Json
      >,
      camelizeDeep,
    ),
    prStatusByWorkspaceId: mapValues(
      update.pr_status_by_workspace_id as unknown as Record<string, Json>,
      camelizeDeep,
    ),
    finishedRequestIds: update.finished_request_ids,
    dependenciesStatus:
      update.dependencies_status === null
        ? null
        : camelizeDeep(update.dependencies_status),
    workspaceSetupStatusByWorkspaceId: mapValues(
      update.workspace_setup_status_by_workspace_id as unknown as Record<
        string,
        Json
      >,
      camelizeDeep,
    ),
    workspaceSetupOutputByWorkspaceId: mapValues(
      update.workspace_setup_output_by_workspace_id as unknown as Record<
        string,
        unknown[]
      >,
      arrayValue,
    ),
    btwUpdate:
      update.btw_update === null ? null : camelizeDeep(update.btw_update),
    uiOpenFileByWorkspaceId: mapValues(
      update.ui_open_file_by_workspace_id as unknown as Record<string, Json>,
      camelizeDeep,
    ),
    uiWebviewCommandByWorkspaceId: mapValues(
      update.ui_webview_command_by_workspace_id as unknown as Record<
        string,
        Json
      >,
      camelizeDeep,
    ),
  };
}
