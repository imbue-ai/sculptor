// Claude-harness error types. These mirror the Python
// `sculptor.interfaces.agents.errors` hierarchy that the Claude code path
// raises; Task 5.6 centralizes the cross-harness error taxonomy, at which point
// these re-home into a shared `harness/errors.ts`. Until then they live here so
// Task 5.3 can surface them.

// A SerializedException-shaped object, matching what `message_conversion.ts`
// (Task 4.2) folds out of `RequestFailure`/crash messages: `{ exception, args,
// traceback_dict }`. The harness emits errors in this shape so the projection
// renders them identically to the Python backend.
export interface SerializedException {
  exception: string;
  args: unknown[];
  traceback_dict: unknown;
}

// Base for errors the agent CLI surfaces. `exitCode` is the CLI process exit
// code when known (null when the error is raised before/without an exit).
export class AgentClientError extends Error {
  readonly exitCode: number | null;

  constructor(message: string, exitCode: number | null = null) {
    super(message);
    this.name = "AgentClientError";
    this.exitCode = exitCode;
  }

  // Render this error as the SerializedException dict the projection folds.
  toSerialized(): SerializedException {
    return { exception: this.name, args: [this.message], traceback_dict: null };
  }
}

// A retryable CLI error (HTTP 429/500/529 or a usage-limit rejection). The
// supervisor / wrapper may retry the turn rather than fail it hard.
export class AgentTransientError extends AgentClientError {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "AgentTransientError";
  }
}

// Claude API error (non-transient HTTP error). Mirrors
// `claude_code_sdk/errors.py:ClaudeAPIError`.
export class ClaudeAPIError extends AgentClientError {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "ClaudeAPIError";
  }
}

// Raised when the `claude` binary cannot be resolved on the host. Mirrors
// `interfaces/agents/errors.py:ClaudeBinaryNotFoundError`.
export class ClaudeBinaryNotFoundError extends AgentClientError {
  constructor() {
    super("Claude binary not found or is invalid.", null);
    this.name = "ClaudeBinaryNotFoundError";
  }
}

// Build a SerializedException dict from any thrown value.
export function serializeError(error: unknown): SerializedException {
  if (error instanceof AgentClientError) {
    return error.toSerialized();
  }
  if (error instanceof Error) {
    return {
      exception: error.name,
      args: [error.message],
      traceback_dict: null,
    };
  }
  return { exception: "Error", args: [String(error)], traceback_dict: null };
}
