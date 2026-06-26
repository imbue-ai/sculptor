// TypeScript types for the frontend `ChatMessage` wire contract.
//
// Ported from `sculptor/sculptor/state/chat_state.py`. These shapes are the
// frontend contract: the fold output MUST serialize to
// JSON identical to the Python `ChatMessage.model_dump(mode="json")`, modulo
// non-load-bearing key ordering. Field names, defaults, and the
// `object_type`/`type` discriminators are therefore reproduced exactly.

// --- Content blocks -------------------------------------------------------

export interface TextBlock {
  object_type: "TextBlock";
  type: "text";
  text: string;
}

export interface ContextSummaryBlock {
  object_type: "ContextSummaryBlock";
  type: "context_summary";
  text: string;
}

export interface ContextClearedBlock {
  object_type: "ContextClearedBlock";
  type: "context_cleared";
  text: string;
}

export interface ResumeResponseBlock {
  object_type: "ResumeResponseBlock";
  type: "resume_response";
}

export type ToolInput = Record<string, unknown>;

// The interactive-backchannel role of a tool, when it is one. `null` for a
// regular tool. Stamped server-side from the harness (`classifyToolUiRole`).
export type ToolInteractiveRole = "ask_user_question" | "exit_plan_mode";

export interface ToolUseBlock {
  object_type: "ToolUseBlock";
  type: "tool_use";
  id: string;
  name: string;
  input: ToolInput;
  interactive_role: ToolInteractiveRole | null;
}

// Tool result content. The Python union is `GenericToolContent | DiffToolContent`
// on `ToolResultBlock`, and `SimpleToolContent` on `ToolResultBlockSimple`. Each
// carries a `content_type` discriminator.
export interface GenericToolContent {
  content_type: "generic";
  text: string;
}

export interface DiffToolContent {
  content_type: "diff";
  diff: string;
  file_path: string;
}

export interface SimpleToolContent {
  content_type: "simple";
  text: string;
  tool_input: ToolInput;
  tool_content: unknown;
}

export type ToolResultContentType = GenericToolContent | DiffToolContent;

export interface ToolResultBlock {
  object_type: "ToolResultBlock";
  type: "tool_result";
  tool_use_id: string;
  tool_name: string;
  invocation_string: string;
  content: ToolResultContentType;
  is_error: boolean;
  duration_seconds: number | null;
  interactive_role: ToolInteractiveRole | null;
  description: string | null;
}

export interface ToolResultBlockSimple {
  object_type: "ToolResultBlockSimple";
  type: "tool_result_simple";
  tool_use_id: string;
  tool_name: string;
  invocation_string: string;
  content: SimpleToolContent;
  is_error: boolean;
  duration_seconds: number | null;
  description: string | null;
}

export interface WarningBlock {
  object_type: "WarningBlock";
  type: "warning";
  message: string;
  traceback: string | null;
  warning_type: string | null;
}

export interface ErrorBlock {
  object_type: "ErrorBlock";
  type: "error";
  message: string;
  traceback: string;
  error_type: string;
}

export interface FileBlock {
  object_type: "FileBlock";
  type: "file";
  source: string;
}

// The discriminated union of content block variants a `ChatMessage` may hold.
// Mirrors `ContentBlockTypes` in chat_state.py (which omits the *Simple block
// variants; they are not part of `ContentBlockTypes`).
export type ContentBlock =
  | TextBlock
  | ToolUseBlock
  | ToolResultBlock
  | ErrorBlock
  | WarningBlock
  | ContextSummaryBlock
  | ContextClearedBlock
  | ResumeResponseBlock
  | FileBlock;

// --- Turn metrics ---------------------------------------------------------

export interface TurnMetrics {
  duration_seconds: number;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  changed_files: string[];
  context_total_tokens: number | null;
  auto_compact_threshold: number | null;
}

// --- ChatMessage ----------------------------------------------------------

export type ChatMessageRole = "USER" | "ASSISTANT";

export interface ChatMessage {
  role: ChatMessageRole;
  id: string;
  content: ContentBlock[];
  parent_tool_use_id: string | null;
  approximate_creation_time: string;
  turn_metrics: TurnMetrics | null;
  stopped: boolean;
  sent_via: string | null;
}

// --- Ask-user-question payload (page-reload reconstruction) ---------------

export interface QuestionOption {
  label: string;
  description: string;
}

export interface UserQuestion {
  question: string;
  header: string;
  options: QuestionOption[];
  multi_select: boolean;
  other_label: string | null;
}

export interface AskUserQuestionData {
  questions: UserQuestion[];
  tool_use_id: string;
  plan_file_path: string | null;
}
