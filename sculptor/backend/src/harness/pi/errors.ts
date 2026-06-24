// Pi-harness error types. Like the Claude harness, these mirror the Python
// `interfaces/agents/errors` hierarchy; Task 5.6 centralizes the cross-harness
// taxonomy, at which point these re-home into a shared module.

import { AgentClientError } from "~/harness/claude/errors";

// Raised when the `pi` binary cannot be resolved on the host.
export class PiBinaryNotFoundError extends AgentClientError {
  constructor() {
    super("Pi binary not found or is invalid.", null);
    this.name = "PiBinaryNotFoundError";
  }
}

// A pi turn failed (preflight rejection, in-stream error, terminal stopReason).
export class PiCrashError extends AgentClientError {
  constructor(message: string, exitCode: number | null = null) {
    super(message, exitCode);
    this.name = "PiCrashError";
  }
}
