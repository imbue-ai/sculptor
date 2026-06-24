// Parsing + framing for pi's JSONL RPC protocol (pi 0.78.0), ported from
// `pi_agent/output_processor.py`. Pi multiplexes three lanes over stdout,
// distinguished by the top-level `type`: command `response` envelopes,
// `extension_ui_request` dialog calls, and the `AgentSessionEvent` union. The
// wire is camelCase; we read it directly. Unknown/malformed payloads parse to a
// `unknown` event the dispatcher ignores (RPC §5.3 forward-compat).

// --- Agent message (the `message` field of message_* events) --------------

export interface PiAgentMessage {
  role: string;
  content: Record<string, unknown>[];
  stopReason: string | null;
  model: string | null;
  errorMessage: string | null;
}

function asAgentMessage(raw: unknown): PiAgentMessage {
  const m = (raw ?? {}) as Record<string, unknown>;
  return {
    role: typeof m.role === "string" ? m.role : "",
    content: Array.isArray(m.content)
      ? (m.content as Record<string, unknown>[])
      : [],
    stopReason: typeof m.stopReason === "string" ? m.stopReason : null,
    model: typeof m.model === "string" ? m.model : null,
    errorMessage: typeof m.errorMessage === "string" ? m.errorMessage : null,
  };
}

export function extractAssistantText(message: PiAgentMessage): string {
  return message.content
    .filter((b) => b.type === "text" && typeof b.text === "string")
    .map((b) => b.text as string)
    .join("");
}

// --- Failure-reason humanization (output_processor.humanize_pi_failure_reason) -

const AUTH_FAILURE_MARKERS = [
  "api key",
  "apikey",
  "api_key",
  "authentication",
  "unauthorized",
  "unauthenticated",
  "401",
  "403",
  "forbidden",
  "permission denied",
  "credential",
];
const UNKNOWN_MODEL_MARKERS = [
  "model not found",
  "unknown model",
  "model_not_found",
  "no such model",
  "model does not exist",
];
const AUTH_FAILURE_MESSAGE =
  "This model isn't available — it may require authentication with its provider. Try another model.";
const UNKNOWN_MODEL_MESSAGE =
  "This model isn't available — it may not exist or isn't enabled for your account. Try another model.";
const GENERIC_FAILURE_MESSAGE =
  "The model failed to complete this turn. Try again, or switch to another model.";

export function humanizePiFailureReason(
  reason: string | null | undefined,
): string {
  const cleaned = (reason ?? "").trim();
  const lowered = cleaned.toLowerCase();
  if (AUTH_FAILURE_MARKERS.some((m) => lowered.includes(m))) {
    return `${AUTH_FAILURE_MESSAGE}\n\nDetails: ${cleaned}`;
  }
  if (UNKNOWN_MODEL_MARKERS.some((m) => lowered.includes(m))) {
    return `${UNKNOWN_MODEL_MESSAGE}\n\nDetails: ${cleaned}`;
  }
  return cleaned || GENERIC_FAILURE_MESSAGE;
}

// --- Parsed event union ---------------------------------------------------

export type PiEvent =
  | {
      kind: "response";
      command: string;
      success: boolean;
      id: string | null;
      error: string | null;
      data: Record<string, unknown> | null;
    }
  | {
      kind: "extension_ui_request";
      id: string;
      method: string;
      title: string | null;
      options: string[] | null;
      message: string | null;
    }
  | { kind: "agent_start" }
  | { kind: "agent_end"; messages: PiAgentMessage[]; willRetry: boolean }
  | {
      kind: "message_update";
      message: PiAgentMessage;
      assistantMessageEvent: Record<string, unknown>;
    }
  | { kind: "message_end"; message: PiAgentMessage }
  | {
      kind: "tool_execution_start";
      toolCallId: string;
      toolName: string;
      args: Record<string, unknown>;
    }
  | {
      kind: "tool_execution_update";
      toolCallId: string;
      partialResult: unknown;
    }
  | {
      kind: "tool_execution_end";
      toolCallId: string;
      toolName: string;
      result: unknown;
      isError: boolean;
    }
  | { kind: "compaction_start" }
  | { kind: "compaction_end" }
  | { kind: "auto_retry_end"; success: boolean; finalError: string | null }
  | { kind: "extension_error"; extensionPath: string; error: string }
  | { kind: "unknown" };

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

// Parse one pi stdout line. Returns null for blank / non-JSON / non-object
// lines (the dispatcher skips them); an unrecognized `type` becomes
// `{ kind: "unknown" }`.
export function parsePiEvent(line: string): PiEvent | null {
  const trimmed = line.trim();
  if (trimmed === "") {
    return null;
  }
  let data: unknown;
  try {
    data = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const d = data as Record<string, unknown>;
  switch (d.type) {
    case "response":
      return {
        kind: "response",
        command: typeof d.command === "string" ? d.command : "",
        success: d.success === true,
        id: typeof d.id === "string" ? d.id : null,
        error: typeof d.error === "string" ? d.error : null,
        data: d.data !== undefined && d.data !== null ? asRecord(d.data) : null,
      };
    case "extension_ui_request":
      return {
        kind: "extension_ui_request",
        id: typeof d.id === "string" ? d.id : "",
        method: typeof d.method === "string" ? d.method : "",
        title: typeof d.title === "string" ? d.title : null,
        options: Array.isArray(d.options) ? (d.options as string[]) : null,
        message: typeof d.message === "string" ? d.message : null,
      };
    case "agent_start":
      return { kind: "agent_start" };
    case "agent_end":
      return {
        kind: "agent_end",
        messages: Array.isArray(d.messages)
          ? d.messages.map(asAgentMessage)
          : [],
        willRetry: d.willRetry === true,
      };
    case "message_update":
      return {
        kind: "message_update",
        message: asAgentMessage(d.message),
        assistantMessageEvent: asRecord(d.assistantMessageEvent),
      };
    case "message_end":
      return { kind: "message_end", message: asAgentMessage(d.message) };
    case "tool_execution_start":
      return {
        kind: "tool_execution_start",
        toolCallId: typeof d.toolCallId === "string" ? d.toolCallId : "",
        toolName: typeof d.toolName === "string" ? d.toolName : "",
        args: asRecord(d.args),
      };
    case "tool_execution_update":
      return {
        kind: "tool_execution_update",
        toolCallId: typeof d.toolCallId === "string" ? d.toolCallId : "",
        partialResult: d.partialResult,
      };
    case "tool_execution_end":
      return {
        kind: "tool_execution_end",
        toolCallId: typeof d.toolCallId === "string" ? d.toolCallId : "",
        toolName: typeof d.toolName === "string" ? d.toolName : "",
        result: d.result,
        isError: d.isError === true,
      };
    case "compaction_start":
      return { kind: "compaction_start" };
    case "compaction_end":
      return { kind: "compaction_end" };
    case "auto_retry_end":
      return {
        kind: "auto_retry_end",
        success: d.success === true,
        finalError: typeof d.finalError === "string" ? d.finalError : null,
      };
    case "extension_error":
      return {
        kind: "extension_error",
        extensionPath:
          typeof d.extensionPath === "string" ? d.extensionPath : "",
        error: typeof d.error === "string" ? d.error : "",
      };
    default:
      return { kind: "unknown" };
  }
}

// --- Stdin RPC command builders -------------------------------------------

export interface PiImage {
  type: "image";
  data: string;
  mimeType: string;
}

export function buildPromptCommand(
  id: string,
  message: string,
  images: PiImage[] = [],
): string {
  const payload: Record<string, unknown> = { type: "prompt", id, message };
  if (images.length > 0) {
    payload.images = images;
  }
  return JSON.stringify(payload) + "\n";
}

export function buildAbortCommand(): string {
  return JSON.stringify({ type: "abort" }) + "\n";
}

export function buildGetStateCommand(id: string): string {
  return JSON.stringify({ type: "get_state", id }) + "\n";
}

export function buildGetAvailableModelsCommand(id: string): string {
  return JSON.stringify({ type: "get_available_models", id }) + "\n";
}

export function buildSetModelCommand(
  id: string,
  provider: string,
  modelId: string,
): string {
  return JSON.stringify({ type: "set_model", id, provider, modelId }) + "\n";
}

export function buildNewSessionCommand(id: string): string {
  return JSON.stringify({ type: "new_session", id }) + "\n";
}

export function buildExtensionUiResponseCommand(
  id: string,
  body: Record<string, unknown>,
): string {
  return JSON.stringify({ type: "extension_ui_response", id, ...body }) + "\n";
}
