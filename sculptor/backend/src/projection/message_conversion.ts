// Folds the append-only agent-message log into the frontend's `ChatMessage[]`.
//
// Ported faithfully from `convert_agent_messages_to_task_update` in
// `sculptor/sculptor/web/message_conversion.py` (the partial-chunk streaming
// fold, tool-use/result pairing, error/warning/context blocks, request
// finalize/stopped/skip, subagent flushing, turn metrics). This is the #1
// parity-drift risk in the rewrite, so the behavior is pinned by golden
// fixtures captured from the real Python function
// (message_conversion.golden.test.ts).
//
// Two entry points:
//   - foldMessages(messages): full fold of an entire log -> ChatMessage[].
//   - applyMessage(state, message): incremental step used by the warm cache
//     (Task 4.4). Incremental application is equivalent to a full re-fold; the
//     golden test asserts this property on every fixture.
//
// Input messages are the raw JSON dicts as stored in agent_message.message
// (Task 2.3): each carries an `object_type` discriminator and the same field
// shapes the Python models serialize to.

import type {
  AskUserQuestionData,
  ChatMessage,
  ContentBlock,
  ErrorBlock,
  TextBlock,
  ToolResultBlock,
  ToolUseBlock,
  TurnMetrics,
  WarningBlock,
} from "~/projection/chat_types";

// --- Harness role classification ------------------------------------------
//
// The conversion stamps tool blocks with their interactive-backchannel role so
// the frontend renders ask-user-question / plan-approval tools by role, not by
// name. The Claude Code harness owns this mapping (its `classify_tool_ui_role`
// composes `is_ask_user_question_tool` / `is_exit_plan_mode_tool`). The fold
// only ever runs against the Claude harness in this rewrite, so the name sets
// are inlined here; mirrors
// `sculptor/sculptor/agents/default/claude_code_sdk/harness.py`.

const ASK_USER_QUESTION_TOOL_NAMES = new Set<string>([
  "AskUserQuestion",
  "mcp__sculptor__ask_user_question",
]);
const EXIT_PLAN_MODE_TOOL_NAMES = new Set<string>([
  "ExitPlanMode",
  "mcp__sculptor__exit_plan_mode",
]);
const ENTER_PLAN_MODE_TOOL_NAMES = new Set<string>([
  "EnterPlanMode",
  "mcp__sculptor__enter_plan_mode",
]);
const PLAN_FILE_WRITE_TOOL_NAMES = new Set<string>(["Write", "Edit", "MultiEdit"]);
const PLAN_FILE_SEGMENT = ".claude/plans/";

function isAskUserQuestionTool(name: string): boolean {
  return ASK_USER_QUESTION_TOOL_NAMES.has(name);
}

function isExitPlanModeTool(name: string): boolean {
  return EXIT_PLAN_MODE_TOOL_NAMES.has(name);
}

function isEnterPlanModeTool(name: string): boolean {
  return ENTER_PLAN_MODE_TOOL_NAMES.has(name);
}

function classifyToolUiRole(name: string): ToolUseBlock["interactive_role"] {
  if (isAskUserQuestionTool(name)) {
    return "ask_user_question";
  }
  if (isExitPlanModeTool(name)) {
    return "exit_plan_mode";
  }
  return null;
}

function planFilePathFromToolUse(block: ContentBlock): string | null {
  if (block.object_type !== "ToolUseBlock") {
    return null;
  }
  if (!PLAN_FILE_WRITE_TOOL_NAMES.has(block.name)) {
    return null;
  }
  const filePath = block.input["file_path"];
  if (typeof filePath === "string" && filePath.includes(PLAN_FILE_SEGMENT)) {
    return filePath;
  }
  return null;
}

// --- Raw message access ---------------------------------------------------

type RawMessage = Record<string, unknown>;

function objectType(message: RawMessage): string {
  return message["object_type"] as string;
}

function asString(value: unknown): string {
  return value as string;
}

function asStringOrNull(value: unknown): string | null {
  return value === undefined || value === null ? null : (value as string);
}

function rawContent(message: RawMessage): ContentBlock[] {
  const content = message["content"];
  return Array.isArray(content) ? (content as ContentBlock[]) : [];
}

// --- Block helpers --------------------------------------------------------

function stampInteractiveRole(block: ContentBlock): ContentBlock {
  if (block.object_type === "ToolUseBlock") {
    return { ...block, interactive_role: classifyToolUiRole(block.name) };
  }
  if (block.object_type === "ToolResultBlock") {
    return { ...block, interactive_role: classifyToolUiRole(block.tool_name) };
  }
  return block;
}

// Port of `split_text_and_media`: extract <img>/<video> tags with local paths
// and supported extensions into interleaved Text/File segments. Persisted
// TextBlocks still contain raw tags; streamed ones are already split upstream.
const IMG_OR_VIDEO_TAG = /<(?:img|video)\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/g;
const SUPPORTED_MEDIA_EXTENSIONS = [
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".bmp",
  ".mp4",
  ".mov",
  ".webm",
  ".avi",
  ".mkv",
];

function hasSupportedMediaExtension(path: string): boolean {
  const lower = path.toLowerCase();
  return SUPPORTED_MEDIA_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function splitTextAndMedia(text: string): ContentBlock[] {
  const matches: { source: string; start: number; end: number }[] = [];
  for (const match of text.matchAll(IMG_OR_VIDEO_TAG)) {
    const source = match[1];
    if (source !== undefined && source.startsWith("/") && hasSupportedMediaExtension(source)) {
      matches.push({ source, start: match.index, end: match.index + match[0].length });
    }
  }
  if (matches.length === 0) {
    const block: TextBlock = { object_type: "TextBlock", type: "text", text };
    return [block];
  }
  const result: ContentBlock[] = [];
  let prevEnd = 0;
  for (const match of matches) {
    const preceding = text.slice(prevEnd, match.start).trim();
    if (preceding) {
      result.push({ object_type: "TextBlock", type: "text", text: preceding });
    }
    result.push({ object_type: "FileBlock", type: "file", source: match.source });
    prevEnd = match.end;
  }
  const trailing = text.slice(prevEnd).trim();
  if (trailing) {
    result.push({ object_type: "TextBlock", type: "text", text: trailing });
  }
  return result;
}

// Python's `str(tuple)` repr, used by SerializedException.as_formatted_traceback
// to render the exception args. Faithfully reproduces 1-tuple `('x',)` and the
// `repr()` of each string arg (single-quoted, backslash-escaped).
function pythonStrRepr(value: string): string {
  const escaped = value
    .replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t");
  // Python prefers single quotes unless the string contains a single quote and
  // no double quote.
  if (escaped.includes("'") && !escaped.includes('"')) {
    return `"${escaped}"`;
  }
  return `'${escaped.replace(/'/g, "\\'")}'`;
}

function pythonTupleRepr(args: unknown[]): string {
  const parts = args.map((arg) =>
    typeof arg === "string" ? pythonStrRepr(arg) : String(arg),
  );
  if (parts.length === 1) {
    return `(${parts[0]},)`;
  }
  return `(${parts.join(", ")})`;
}

interface SerializedError {
  exception: string;
  args: unknown[];
  traceback_dict: unknown;
}

function readSerializedError(value: unknown): SerializedError {
  const error = value as Record<string, unknown>;
  return {
    exception: error["exception"] as string,
    args: Array.isArray(error["args"]) ? (error["args"] as unknown[]) : [],
    traceback_dict: error["traceback_dict"],
  };
}

// Mirrors SerializedException.as_formatted_traceback. When traceback_dict is
// null the traceback section is empty (the case captured in fixtures); a
// concrete traceback would render via Python's format_tb, which is not
// reproduced here (out of scope — the live error path never folds with a
// populated traceback in these fixtures).
function formatTraceback(error: SerializedError): string {
  return `Traceback (most recent call last):\n\n${error.exception}: ${pythonTupleRepr(error.args)}`;
}

// --- ChatMessage helpers --------------------------------------------------

function createEmptyAssistantMessage(
  chatMessageId: string,
  approximateCreationTime: string,
  parentToolUseId: string | null = null,
): ChatMessage {
  return {
    role: "ASSISTANT",
    id: chatMessageId,
    content: [],
    parent_tool_use_id: parentToolUseId,
    approximate_creation_time: approximateCreationTime,
    turn_metrics: null,
    stopped: false,
    sent_via: null,
  };
}

// Try to replace a tool_use block with its result. Returns whether it replaced.
function replaceToolUseWithResult(
  content: ContentBlock[],
  result: ToolResultBlock,
): boolean {
  for (let i = 0; i < content.length; i++) {
    const block = content[i];
    if (block !== undefined && block.object_type === "ToolUseBlock" && block.id === result.tool_use_id) {
      // AskUserQuestion / ExitPlanMode tool_use blocks must remain (the
      // frontend renders custom components keyed on type === "tool_use").
      if (isAskUserQuestionTool(block.name) || isExitPlanModeTool(block.name)) {
        return true;
      }
      // Agent/Task tool_use blocks must remain so the subagent pill renders;
      // insert the result after the tool_use instead of replacing it.
      if (block.name === "Agent" || block.name === "Task") {
        const alreadyHasResult = content.some(
          (b) => b.object_type === "ToolResultBlock" && b.tool_use_id === result.tool_use_id,
        );
        if (!alreadyHasResult) {
          content.splice(i + 1, 0, result);
        }
        return true;
      }
      content[i] = result;
      return true;
    }
  }
  return false;
}

// Process response blocks (text/tool_use append, tool_result replace-or-append).
// Two passes so ToolUseBlocks exist before ToolResultBlocks try to replace them.
function handleResponseBlocks(
  inProgress: ChatMessage | null,
  blocks: ContentBlock[],
  agentMessageId: string,
  approximateCreationTime: string,
  parentToolUseId: string | null = null,
): ChatMessage {
  let message =
    inProgress ?? createEmptyAssistantMessage(agentMessageId, approximateCreationTime, parentToolUseId);
  const content = [...message.content];
  const existingToolUseIds = new Set(
    content.filter((b) => b.object_type === "ToolUseBlock").map((b) => (b as ToolUseBlock).id),
  );
  const toolResultBlocks: ToolResultBlock[] = [];

  for (const block of blocks) {
    if (block.object_type === "TextBlock") {
      content.push(...splitTextAndMedia(block.text));
    } else if (block.object_type === "FileBlock") {
      content.push(block);
    } else if (block.object_type === "ToolUseBlock") {
      if (!existingToolUseIds.has(block.id)) {
        if (classifyToolUiRole(block.name) !== null) {
          // For backchannel tools, drop any earlier ToolResultBlock for this id.
          for (let i = content.length - 1; i >= 0; i--) {
            const existing = content[i];
            if (existing !== undefined && existing.object_type === "ToolResultBlock" && existing.tool_use_id === block.id) {
              content.splice(i, 1);
            }
          }
        }
        content.push(stampInteractiveRole(block));
        existingToolUseIds.add(block.id);
      }
    } else if (block.object_type === "ToolResultBlock") {
      toolResultBlocks.push(block);
    }
  }

  for (const block of toolResultBlocks) {
    const stamped: ToolResultBlock = {
      ...block,
      interactive_role: classifyToolUiRole(block.tool_name),
    };
    const replaced = replaceToolUseWithResult(content, stamped);
    if (!replaced) {
      content.push(stamped);
    }
  }

  message = { ...message, content };
  return message;
}

// Re-insert ToolUseBlocks that a mid-stream tool_result overwrote in place
// (SCU-512). Each is inserted before its matching ToolResultBlock, or appended.
function restoreOverwrittenToolUses(
  inProgress: ChatMessage,
  toolUses: ToolUseBlock[],
): ChatMessage {
  const content = [...inProgress.content];
  for (const toolUse of toolUses) {
    const insertAt = content.findIndex(
      (block) => block.object_type === "ToolResultBlock" && block.tool_use_id === toolUse.id,
    );
    if (insertAt === -1) {
      content.push(toolUse);
    } else {
      content.splice(insertAt, 0, toolUse);
    }
  }
  return { ...inProgress, content };
}

// Streaming partial: replace content from streamingStartIndex onwards.
function handlePartialResponse(
  inProgress: ChatMessage | null,
  content: ContentBlock[],
  messageId: string,
  approximateCreationTime: string,
  streamingStartIndex: number,
  parentToolUseId: string | null,
): ChatMessage {
  const message =
    inProgress ?? createEmptyAssistantMessage(messageId, approximateCreationTime, parentToolUseId);
  const committed = message.content.slice(0, streamingStartIndex);
  const committedToolUseIds = new Set(
    committed.filter((b) => b.object_type === "ToolUseBlock").map((b) => (b as ToolUseBlock).id),
  );
  const deduplicated = content
    .filter((b) => !(b.object_type === "ToolUseBlock" && committedToolUseIds.has(b.id)))
    .map((b) => stampInteractiveRole(b));
  return { ...message, content: [...committed, ...deduplicated] };
}

function addSystemBlockToMessage(
  inProgress: ChatMessage | null,
  block: ContentBlock,
  chatMessageId: string,
  approximateCreationTime: string,
): ChatMessage {
  const message =
    inProgress ?? createEmptyAssistantMessage(chatMessageId, approximateCreationTime);
  return { ...message, content: [...message.content, block] };
}

function addErrorToMessage(inProgress: ChatMessage | null, message: RawMessage): ChatMessage {
  const error = readSerializedError(message["error"]);
  const chatMessageId = asString(message["message_id"]);
  const approximateCreationTime = asString(message["approximate_creation_time"]);
  const args = error.args;
  const messageText = args.length > 0 && typeof args[0] === "string" ? args[0] : `${error.exception}`;
  const errorBlock: ErrorBlock = {
    object_type: "ErrorBlock",
    type: "error",
    message: messageText,
    traceback: formatTraceback(error),
    error_type: error.exception,
  };
  return addSystemBlockToMessage(inProgress, errorBlock, chatMessageId, approximateCreationTime);
}

function addWarningToMessage(inProgress: ChatMessage | null, message: RawMessage): ChatMessage {
  let traceback: string | null = null;
  let warningType: string | null = null;
  const rawError = message["error"];
  if (rawError !== undefined && rawError !== null) {
    const error = readSerializedError(rawError);
    traceback = formatTraceback(error);
    warningType = error.exception;
  }
  const warningBlock: WarningBlock = {
    object_type: "WarningBlock",
    type: "warning",
    message: asString(message["message"]),
    traceback,
    warning_type: warningType,
  };
  return addSystemBlockToMessage(
    inProgress,
    warningBlock,
    asString(message["message_id"]),
    asString(message["approximate_creation_time"]),
  );
}

function addContextSummaryToMessage(message: RawMessage): ChatMessage {
  const block: ContentBlock = {
    object_type: "ContextSummaryBlock",
    type: "context_summary",
    text: asString(message["content"]),
  };
  return addSystemBlockToMessage(
    null,
    block,
    asString(message["message_id"]),
    asString(message["approximate_creation_time"]),
  );
}

function addContextClearedToMessage(message: RawMessage): ChatMessage {
  const block: ContentBlock = {
    object_type: "ContextClearedBlock",
    type: "context_cleared",
    text: "Cleared successfully",
  };
  return addSystemBlockToMessage(
    null,
    block,
    asString(message["message_id"]),
    asString(message["approximate_creation_time"]),
  );
}

// Locate a ToolUseBlock by id; returns the block + the creation time of its
// containing ChatMessage (used to timestamp synthesized background children).
function findToolUseById(
  toolUseId: string,
  inProgress: ChatMessage | null,
  completed: ChatMessage[],
): { block: ToolUseBlock; createdAt: string } | null {
  const candidates: ChatMessage[] = [];
  if (inProgress !== null) {
    candidates.push(inProgress);
  }
  candidates.push(...completed);
  for (const chatMessage of candidates) {
    for (const block of chatMessage.content) {
      if (block.object_type === "ToolUseBlock" && block.id === toolUseId) {
        return { block, createdAt: chatMessage.approximate_creation_time };
      }
    }
  }
  return null;
}

// Add `duration_seconds` to an ISO-8601 UTC timestamp, preserving the exact
// `...Z` / fractional rendering Python's `model_dump(mode="json")` produces.
function addSecondsToTimestamp(timestamp: string, durationSeconds: number): string {
  const millis = Date.parse(timestamp) + durationSeconds * 1000;
  const date = new Date(millis);
  const iso = date.toISOString();
  // toISOString always renders milliseconds (".000Z"); strip a trailing
  // ".000" so an integer-second result matches Python's "...T00:00:06Z" form.
  return iso.replace(/\.000Z$/, "Z");
}

// --- Streaming state ------------------------------------------------------
//
// Groups the variables that control how streaming partials assemble into the
// in-progress message. Ported from `_StreamingState`. The turn-boundary detection
// keys on a CHANGE in `currentSegmentFirstResponseId` (NOT id-equality), which is
// what fixes the "staircase"/double-print bug.

interface StreamingState {
  isActive: boolean;
  startIndex: number;
  pendingToolResults: ToolResultBlock[];
  messageWasStreamed: boolean;
  streamedAssistantMessageIds: Set<string>;
  currentSegmentFirstResponseId: string | null;
}

function newStreamingState(): StreamingState {
  return {
    isActive: false,
    startIndex: 0,
    pendingToolResults: [],
    messageWasStreamed: false,
    streamedAssistantMessageIds: new Set(),
    currentSegmentFirstResponseId: null,
  };
}

function resetStreaming(streaming: StreamingState): void {
  streaming.isActive = false;
  streaming.startIndex = 0;
  streaming.pendingToolResults = [];
  streaming.messageWasStreamed = false;
  streaming.streamedAssistantMessageIds = new Set();
  streaming.currentSegmentFirstResponseId = null;
}

function completeSegment(streaming: StreamingState, contentLength: number): void {
  streaming.startIndex = contentLength;
  streaming.isActive = false;
  streaming.pendingToolResults = [];
}

// --- Fold state -----------------------------------------------------------
//
// The full mutable state carried across a fold. Holds everything Python's
// `TaskUpdate` carries that the incremental fold must preserve so that applying
// one message at a time equals a full re-fold. `completedChatMessages` is the
// accumulator emitted on each step; `completedMessageById` is the cross-batch
// dedupe/turn-boundary index.

export interface FoldState {
  completedChatMessages: ChatMessage[];
  completedMessageById: Map<string, ChatMessage>;
  queuedChatMessages: ChatMessage[];
  inProgressChatMessage: ChatMessage | null;
  currentRequestId: string | null;
  pendingTurnMetrics: TurnMetrics | null;
  pendingUserQuestion: AskUserQuestionData | null;
  submittedQuestionToolUseIds: Set<string>;
  // Answered questions keyed by tool_use_id, carrying the data the frontend
  // needs to render the answered AUQ/plan tool block in history (the question +
  // the user's selection). Mirrors TaskUpdate.submitted_question_answers.
  submittedQuestionAnswers: Map<string, SubmittedQuestionAnswer>;
  pendingBackgroundTaskIds: Set<string>;
  recentPlanFilePath: string | null;
  // Whether the agent is currently in plan mode. Set by the EnterPlanMode tool
  // and the user's enter_plan_mode/exit_plan_mode chat-input flags; cleared by
  // ExitPlanMode. Distinct from recentPlanFilePath (a written plan file).
  isInPlanMode: boolean;
  // Artifact types seen via UpdatedArtifactAgentMessage (e.g. "PLAN", "DIFF").
  // Surfaced as task_update.updated_artifacts so the frontend fetches them.
  updatedArtifacts: Set<string>;
  streaming: StreamingState;
}

export interface SubmittedQuestionAnswer {
  question_data: AskUserQuestionData;
  answers: Record<string, string>;
  tool_use_id: string;
}

export function createFoldState(): FoldState {
  return {
    completedChatMessages: [],
    completedMessageById: new Map(),
    queuedChatMessages: [],
    inProgressChatMessage: null,
    currentRequestId: null,
    pendingTurnMetrics: null,
    pendingUserQuestion: null,
    submittedQuestionToolUseIds: new Set(),
    submittedQuestionAnswers: new Map(),
    pendingBackgroundTaskIds: new Set(),
    recentPlanFilePath: null,
    isInPlanMode: false,
    updatedArtifacts: new Set(),
    streaming: newStreamingState(),
  };
}

function finalizeRequest(state: FoldState, requestId: string): void {
  if (state.currentRequestId === null || requestId !== state.currentRequestId) {
    return;
  }
  if (state.inProgressChatMessage !== null) {
    state.completedMessageById.set(state.inProgressChatMessage.id, state.inProgressChatMessage);
    state.completedChatMessages.push(state.inProgressChatMessage);
    state.inProgressChatMessage = null;
  }
  state.currentRequestId = null;
}

function markStopped(message: ChatMessage | null): ChatMessage | null {
  if (message === null) {
    return null;
  }
  return { ...message, stopped: true };
}

function attachTurnMetrics(
  message: ChatMessage | null,
  turnMetrics: TurnMetrics | null,
): ChatMessage | null {
  if (message === null || turnMetrics === null) {
    return message;
  }
  return { ...message, turn_metrics: turnMetrics };
}

function reconstructPendingAskUserQuestion(block: ToolUseBlock): AskUserQuestionData | null {
  // Claude's MCP AskUserQuestion tool input carries the AskUserQuestionData
  // fields directly. The Python harness strict-validates the questions; here we
  // require a `questions` array. (The malformed-input fixtures exercise the
  // rejection.)
  const questions = block.input["questions"];
  if (!Array.isArray(questions)) {
    return null;
  }
  return {
    questions: questions as AskUserQuestionData["questions"],
    tool_use_id: block.id,
    plan_file_path: null,
  };
}

function makePlanApprovalQuestion(toolUseId: string, planFilePath: string | null): AskUserQuestionData {
  return {
    questions: [
      {
        question: "Planning complete. How would you like to proceed?",
        header: "Plan approval",
        options: [{ label: "Approve plan", description: "Proceed with implementing the plan" }],
        multi_select: false,
        other_label: "Revise",
      },
    ],
    tool_use_id: toolUseId,
    plan_file_path: planFilePath,
  };
}

// --- The fold step --------------------------------------------------------

export function applyMessage(state: FoldState, message: RawMessage): FoldState {
  const type = objectType(message);
  const streaming = state.streaming;

  if (type === "ChatInputUserMessage") {
    // Reflect the plan-mode toggle from the user message immediately, before the
    // agent processes it (message_conversion.py L249-252).
    if (message["enter_plan_mode"] === true) {
      state.isInPlanMode = true;
    } else if (message["exit_plan_mode"] === true) {
      state.isInPlanMode = false;
    }
    const text = asString(message["text"]);
    const content: ContentBlock[] = [{ object_type: "TextBlock", type: "text", text }];
    const files = message["files"];
    if (Array.isArray(files)) {
      for (const file of files) {
        content.push({ object_type: "FileBlock", type: "file", source: asString(file) });
      }
    }
    const messageId = asString(message["message_id"]);
    const isAlreadyCompleted = state.completedMessageById.has(messageId);
    const isAlreadyQueued = state.queuedChatMessages.some((queued) => queued.id === messageId);
    if (!isAlreadyCompleted && !isAlreadyQueued) {
      state.queuedChatMessages.push({
        role: "USER",
        id: messageId,
        content,
        parent_tool_use_id: null,
        approximate_creation_time: asString(message["approximate_creation_time"]),
        turn_metrics: null,
        stopped: false,
        sent_via: asStringOrNull(message["sent_via"]),
      });
    }
  } else if (type === "RequestStartedAgentMessage") {
    const requestId = asString(message["request_id"]);
    let isPromoted = false;
    for (let i = 0; i < state.queuedChatMessages.length; i++) {
      const queued = state.queuedChatMessages[i];
      if (queued !== undefined && queued.id === requestId) {
        state.queuedChatMessages.splice(i, 1);
        state.completedMessageById.set(queued.id, queued);
        state.completedChatMessages.push(queued);
        isPromoted = true;
        break;
      }
    }
    if (isPromoted || state.currentRequestId === null) {
      state.currentRequestId = requestId;
    }
  } else if (type === "RemoveQueuedMessageAgentMessage") {
    const removedId = asString(message["removed_message_id"]);
    state.queuedChatMessages = state.queuedChatMessages.filter((m) => m.id !== removedId);
  } else if (type === "PartialResponseBlockAgentMessage") {
    const msgParent = asStringOrNull(message["parent_tool_use_id"]);
    const firstResponseId = asString(message["first_response_message_id"]);
    if (state.inProgressChatMessage !== null) {
      const currentParent = state.inProgressChatMessage.parent_tool_use_id;
      const startsNewStreamedTurn =
        streaming.currentSegmentFirstResponseId !== null &&
        streaming.currentSegmentFirstResponseId !== firstResponseId &&
        !state.completedMessageById.has(firstResponseId);
      if (msgParent !== currentParent) {
        state.completedMessageById.set(state.inProgressChatMessage.id, state.inProgressChatMessage);
        state.completedChatMessages.push(state.inProgressChatMessage);
        state.inProgressChatMessage = null;
        resetStreaming(streaming);
      } else if (startsNewStreamedTurn) {
        completeSegment(streaming, state.inProgressChatMessage.content.length);
      }
    }
    if (!streaming.isActive) {
      streaming.startIndex =
        state.inProgressChatMessage !== null ? state.inProgressChatMessage.content.length : 0;
    }
    streaming.isActive = true;
    streaming.messageWasStreamed = true;
    streaming.currentSegmentFirstResponseId = firstResponseId;
    streaming.streamedAssistantMessageIds.add(asString(message["assistant_message_id"]));
    state.inProgressChatMessage = handlePartialResponse(
      state.inProgressChatMessage,
      rawContent(message),
      firstResponseId,
      asString(message["approximate_creation_time"]),
      streaming.startIndex,
      msgParent,
    );
    for (const result of streaming.pendingToolResults) {
      const inProgress: ChatMessage = state.inProgressChatMessage;
      const content = [...inProgress.content];
      replaceToolUseWithResult(content, result);
      state.inProgressChatMessage = { ...inProgress, content };
    }
  } else if (type === "ResponseBlockAgentMessage") {
    const msgParent = asStringOrNull(message["parent_tool_use_id"]);
    const blocks = rawContent(message);
    const messageId = asString(message["message_id"]);
    const approximateCreationTime = asString(message["approximate_creation_time"]);
    const assistantMessageId = asString(message["assistant_message_id"]);

    if (streaming.isActive) {
      const currentParent =
        state.inProgressChatMessage !== null ? state.inProgressChatMessage.parent_tool_use_id : null;
      if (msgParent !== currentParent) {
        const separate = handleResponseBlocks(null, blocks, messageId, approximateCreationTime, msgParent);
        state.completedMessageById.set(separate.id, separate);
        state.completedChatMessages.push(separate);
        return state;
      }
      const nonStreamedBlocks = blocks.filter(
        (block): block is ToolResultBlock => block.object_type === "ToolResultBlock",
      );
      if (nonStreamedBlocks.length > 0) {
        state.inProgressChatMessage = handleResponseBlocks(
          state.inProgressChatMessage,
          nonStreamedBlocks,
          messageId,
          approximateCreationTime,
        );
        streaming.pendingToolResults.push(...nonStreamedBlocks);
      }
      return state;
    }

    const currentParent =
      state.inProgressChatMessage !== null ? state.inProgressChatMessage.parent_tool_use_id : null;
    if (msgParent !== currentParent) {
      if (msgParent !== null) {
        const separate = handleResponseBlocks(null, blocks, messageId, approximateCreationTime, msgParent);
        state.completedMessageById.set(separate.id, separate);
        state.completedChatMessages.push(separate);
        return state;
      }
      if (state.inProgressChatMessage !== null) {
        state.completedMessageById.set(state.inProgressChatMessage.id, state.inProgressChatMessage);
        state.completedChatMessages.push(state.inProgressChatMessage);
        state.inProgressChatMessage = null;
        streaming.messageWasStreamed = false;
      }
    }

    const isAlreadyCompleted = state.completedMessageById.has(messageId);
    const isAssistantAlreadyStreamed = streaming.streamedAssistantMessageIds.has(assistantMessageId);
    if (streaming.messageWasStreamed || isAlreadyCompleted || isAssistantAlreadyStreamed) {
      const existingFileSources = new Set<string>();
      if (state.inProgressChatMessage !== null) {
        for (const block of state.inProgressChatMessage.content) {
          if (block.object_type === "FileBlock") {
            existingFileSources.add(block.source);
          }
        }
      }
      const nonStreamedBlocks = blocks.filter(
        (block) =>
          block.object_type === "ToolResultBlock" ||
          (block.object_type === "FileBlock" && !existingFileSources.has(block.source)),
      );
      if (nonStreamedBlocks.length > 0) {
        state.inProgressChatMessage = handleResponseBlocks(
          state.inProgressChatMessage,
          nonStreamedBlocks,
          messageId,
          approximateCreationTime,
        );
      }
      if (state.inProgressChatMessage !== null) {
        const existingToolUseIds = new Set(
          state.inProgressChatMessage.content
            .filter((b) => b.object_type === "ToolUseBlock")
            .map((b) => (b as ToolUseBlock).id),
        );
        const restoredToolUses = blocks.filter(
          (block): block is ToolUseBlock =>
            block.object_type === "ToolUseBlock" && !existingToolUseIds.has(block.id),
        );
        if (restoredToolUses.length > 0) {
          state.inProgressChatMessage = restoreOverwrittenToolUses(
            state.inProgressChatMessage,
            restoredToolUses,
          );
        }
      }
    } else {
      state.inProgressChatMessage = handleResponseBlocks(
        state.inProgressChatMessage,
        blocks,
        messageId,
        approximateCreationTime,
        msgParent,
      );
    }

    for (const block of blocks) {
      const planPath = planFilePathFromToolUse(block);
      if (planPath !== null) {
        state.recentPlanFilePath = planPath;
      }
      if (block.object_type === "ToolUseBlock" && isAskUserQuestionTool(block.name)) {
        if (!state.submittedQuestionToolUseIds.has(block.id)) {
          const reconstructed = reconstructPendingAskUserQuestion(block);
          if (reconstructed !== null) {
            state.pendingUserQuestion = reconstructed;
          }
        }
      } else if (block.object_type === "ToolUseBlock" && isEnterPlanModeTool(block.name)) {
        state.isInPlanMode = true;
      } else if (block.object_type === "ToolUseBlock" && isExitPlanModeTool(block.name)) {
        if (!state.submittedQuestionToolUseIds.has(block.id)) {
          state.pendingUserQuestion = makePlanApprovalQuestion(block.id, state.recentPlanFilePath);
        }
        state.recentPlanFilePath = null;
        state.isInPlanMode = false;
      }
    }
  } else if (type === "StreamingMessageCompleteAgentMessage") {
    completeSegment(
      streaming,
      state.inProgressChatMessage !== null ? state.inProgressChatMessage.content.length : 0,
    );
  } else if (type === "ResumeAgentResponseRunnerMessage") {
    state.inProgressChatMessage = handleResponseBlocks(
      state.inProgressChatMessage,
      [{ object_type: "ResumeResponseBlock", type: "resume_response" }],
      asString(message["message_id"]),
      asString(message["approximate_creation_time"]),
    );
  } else if (type === "ContextSummaryMessage") {
    if (state.inProgressChatMessage !== null) {
      state.completedMessageById.set(state.inProgressChatMessage.id, state.inProgressChatMessage);
      state.completedChatMessages.push(state.inProgressChatMessage);
      state.inProgressChatMessage = null;
      resetStreaming(streaming);
    }
    const summary = addContextSummaryToMessage(message);
    state.completedMessageById.set(summary.id, summary);
    state.completedChatMessages.push(summary);
  } else if (type === "ContextClearedMessage") {
    if (state.inProgressChatMessage !== null) {
      state.completedMessageById.set(state.inProgressChatMessage.id, state.inProgressChatMessage);
      state.completedChatMessages.push(state.inProgressChatMessage);
      state.inProgressChatMessage = null;
      resetStreaming(streaming);
    }
    const cleared = addContextClearedToMessage(message);
    state.completedMessageById.set(cleared.id, cleared);
    state.completedChatMessages.push(cleared);
  } else if (type === "TurnMetricsAgentMessage") {
    state.pendingTurnMetrics = message["turn_metrics"] as TurnMetrics;
  } else if (type === "RequestSuccessAgentMessage") {
    const requestId = asString(message["request_id"]);
    const interrupted = message["interrupted"] === true;
    const canFinalize = state.currentRequestId !== null && state.currentRequestId === requestId;
    const hasPendingReplacement = state.queuedChatMessages.length > 0;
    if (state.inProgressChatMessage === null && interrupted && canFinalize && !hasPendingReplacement) {
      state.inProgressChatMessage = createEmptyAssistantMessage(
        asString(message["message_id"]),
        asString(message["approximate_creation_time"]),
      );
    }
    if (interrupted) {
      state.inProgressChatMessage = markStopped(state.inProgressChatMessage);
      state.pendingUserQuestion = null;
    }
    state.inProgressChatMessage = attachTurnMetrics(state.inProgressChatMessage, state.pendingTurnMetrics);
    state.pendingTurnMetrics = null;
    finalizeRequest(state, requestId);
    resetStreaming(streaming);
    state.pendingBackgroundTaskIds.clear();
  } else if (type === "RequestFailureAgentMessage") {
    state.inProgressChatMessage = addErrorToMessage(state.inProgressChatMessage, message);
    state.pendingUserQuestion = null;
    finalizeRequest(state, asString(message["request_id"]));
    resetStreaming(streaming);
    state.pendingBackgroundTaskIds.clear();
  } else if (type === "RequestStoppedAgentMessage") {
    const requestId = asString(message["request_id"]);
    const canFinalize = state.currentRequestId !== null && state.currentRequestId === requestId;
    if (canFinalize) {
      state.inProgressChatMessage = markStopped(state.inProgressChatMessage);
      state.inProgressChatMessage = attachTurnMetrics(state.inProgressChatMessage, state.pendingTurnMetrics);
      state.pendingTurnMetrics = null;
      state.pendingUserQuestion = null;
    }
    finalizeRequest(state, requestId);
    resetStreaming(streaming);
    state.pendingBackgroundTaskIds.clear();
  } else if (type === "RequestSkippedAgentMessage") {
    finalizeRequest(state, asString(message["request_id"]));
    resetStreaming(streaming);
    state.pendingBackgroundTaskIds.clear();
  } else if (
    type === "EnvironmentCrashedRunnerMessage" ||
    type === "UnexpectedErrorRunnerMessage" ||
    type === "AgentCrashedRunnerMessage"
  ) {
    if (state.inProgressChatMessage !== null) {
      state.inProgressChatMessage = addErrorToMessage(state.inProgressChatMessage, message);
    } else {
      const newMessage = addErrorToMessage(null, message);
      state.completedMessageById.set(newMessage.id, newMessage);
      state.completedChatMessages.push(newMessage);
    }
  } else if (type === "WarningAgentMessage") {
    if (state.inProgressChatMessage !== null) {
      state.inProgressChatMessage = addWarningToMessage(state.inProgressChatMessage, message);
    } else {
      const newMessage = addWarningToMessage(null, message);
      state.completedMessageById.set(newMessage.id, newMessage);
      state.completedChatMessages.push(newMessage);
    }
  } else if (type === "BackgroundTaskStartedAgentMessage") {
    state.pendingBackgroundTaskIds.add(asString(message["background_task_id"]));
  } else if (type === "BackgroundTaskNotificationAgentMessage") {
    const toolUseId = asString(message["tool_use_id"]);
    state.pendingBackgroundTaskIds.delete(asString(message["background_task_id"]));
    const parentToolUse = findToolUseById(toolUseId, state.inProgressChatMessage, state.completedChatMessages);
    if (parentToolUse !== null && parentToolUse.block.name !== "Agent" && parentToolUse.block.name !== "Task") {
      return state;
    }
    let creationTime = asString(message["approximate_creation_time"]);
    const durationSeconds = message["duration_seconds"];
    if (typeof durationSeconds === "number" && parentToolUse !== null) {
      creationTime = addSecondsToTimestamp(parentToolUse.createdAt, durationSeconds);
    }
    const synthetic: ChatMessage = {
      role: "ASSISTANT",
      id: asString(message["message_id"]),
      content: [{ object_type: "TextBlock", type: "text", text: asString(message["summary"]) }],
      parent_tool_use_id: toolUseId,
      approximate_creation_time: creationTime,
      turn_metrics: null,
      stopped: false,
      sent_via: null,
    };
    state.completedMessageById.set(synthetic.id, synthetic);
    state.completedChatMessages.push(synthetic);
  } else if (type === "AskUserQuestionAgentMessage") {
    const questionData = message["question_data"] as AskUserQuestionData;
    if (!state.submittedQuestionToolUseIds.has(questionData.tool_use_id)) {
      state.pendingUserQuestion = questionData;
    }
  } else if (type === "UserQuestionAnswerMessage") {
    if (state.inProgressChatMessage !== null) {
      state.completedMessageById.set(state.inProgressChatMessage.id, state.inProgressChatMessage);
      state.completedChatMessages.push(state.inProgressChatMessage);
      state.inProgressChatMessage = null;
      streaming.messageWasStreamed = false;
    }
    state.pendingUserQuestion = null;
    state.currentRequestId = asString(message["message_id"]);
    const toolUseId = asString(message["tool_use_id"]);
    state.submittedQuestionToolUseIds.add(toolUseId);
    state.submittedQuestionAnswers.set(toolUseId, {
      question_data: message["question_data"] as AskUserQuestionData,
      answers: (message["answers"] as Record<string, string> | undefined) ?? {},
      tool_use_id: toolUseId,
    });
  } else if (objectType(message) === "UpdatedArtifactAgentMessage") {
    // Record the artifact type (PLAN/DIFF) so task_update.updated_artifacts
    // signals the frontend to fetch it (message_conversion.py L796-799).
    const artifact = message["artifact"] as
      | Record<string, unknown>
      | undefined;
    const name = artifact?.["name"];
    if (typeof name === "string" && name) {
      state.updatedArtifacts.add(name);
    }
  }
  // Other message types (plan-mode, ephemeral lifecycle, etc.) do not affect the
  // ChatMessage list and are intentionally ignored.

  return state;
}

// The visible ChatMessage list for a fold state: completed messages followed by
// the in-progress message (if any). Queued user messages are tracked separately
// and not part of this list (mirrors how the frontend renders them).
export function foldStateToChatMessages(state: FoldState): ChatMessage[] {
  const messages = [...state.completedChatMessages];
  if (state.inProgressChatMessage !== null) {
    messages.push(state.inProgressChatMessage);
  }
  return messages;
}

// Full fold of an entire agent-message log into ChatMessage[]. Faithful port of
// `convert_agent_messages_to_task_update` over a fresh state.
export function foldMessages(messages: RawMessage[]): ChatMessage[] {
  const state = createFoldState();
  for (const message of messages) {
    applyMessage(state, message);
  }
  return foldStateToChatMessages(state);
}
