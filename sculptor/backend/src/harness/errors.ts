// The centralized harness error taxonomy, ported from
// `interfaces/agents/errors.py`. The missing-binary errors must be distinct and
// surfaced so the API/projection render a clear startup-error
// message rather than a generic failure. `claude/errors.ts` and `pi/errors.ts`
// re-export from here so existing import paths keep working.

// A SerializedException-shaped object, matching what `message_conversion.ts`
// folds out of RequestFailure / crash messages.
export interface SerializedException {
  exception: string;
  args: unknown[];
  traceback_dict: unknown;
}

// Base for agent crashes (`AgentCrashed`): a structured mid-run failure or an
// unexpected subprocess exit. `exitCode` is the CLI exit code when known.
export class AgentCrashed extends Error {
  readonly exitCode: number | null;
  readonly metadata: Record<string, unknown> | null;

  constructor(
    message: string,
    exitCode: number | null = null,
    metadata: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "AgentCrashed";
    this.exitCode = exitCode;
    this.metadata = metadata;
  }

  // Render as the SerializedException dict the projection folds.
  toSerialized(): SerializedException {
    return { exception: this.name, args: [this.message], traceback_dict: null };
  }
}

// Raised when the agent's CLI client encounters an error (`AgentClientError`).
export class AgentClientError extends AgentCrashed {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "AgentClientError";
  }
}

// A retryable CLI error (HTTP 429/500/529 or a usage-limit rejection).
export class AgentTransientError extends AgentClientError {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "AgentTransientError";
  }
}

// Claude API error (non-transient HTTP error).
export class ClaudeAPIError extends AgentClientError {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "ClaudeAPIError";
  }
}

// Raised when the `claude` binary cannot be resolved on the host.
export class ClaudeBinaryNotFoundError extends AgentClientError {
  constructor() {
    super("Claude binary not found or is invalid.", null);
    this.name = "ClaudeBinaryNotFoundError";
  }
}

// Raised when the `pi` binary cannot be resolved on the host.
export class PiBinaryNotFoundError extends AgentClientError {
  constructor() {
    super("Pi binary not found or is invalid.", null);
    this.name = "PiBinaryNotFoundError";
  }
}

// Raised when the detected pi version is outside the pinned range.
export class PiVersionMismatchError extends AgentClientError {
  readonly detectedVersion: string;
  readonly pinnedVersion: string;

  constructor(detectedVersion: string, pinnedVersion: string) {
    super(
      `Pi version ${detectedVersion} is outside the pinned range (expected ${pinnedVersion}). ` +
        "Set the pi Binary Source to Managed in Settings to install the pinned version " +
        `automatically, or point pi at a ${pinnedVersion} build.`,
      null,
    );
    this.name = "PiVersionMismatchError";
    this.detectedVersion = detectedVersion;
    this.pinnedVersion = pinnedVersion;
  }
}

// Raised when pi reports a structured error mid-turn or its subprocess exits
// unexpectedly. Extends `AgentCrashed` directly (mirrors Python).
export class PiCrashError extends AgentCrashed {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "PiCrashError";
  }
}

// Build a SerializedException dict from any thrown value.
export function serializeError(error: unknown): SerializedException {
  if (error instanceof AgentCrashed) {
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
