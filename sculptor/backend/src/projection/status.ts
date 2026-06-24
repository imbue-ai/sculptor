// The derived UI `status` computation for an agent.
//
// Ported faithfully from `sculptor/sculptor/web/derived.py`:
//   - `TaskStatus` (the derived UI status enum),
//   - `_maybe_get_status_from_outcome` (the run-state/outcome short-circuit),
//   - `scan_terminal_signal_state` (run-scoped terminal-signal state),
//   - the `CodingAgentTaskView.status` property's branch ORDER, plus its helpers
//     `_ready_or_waiting` and `_last_request_failed`.
//
// The branch order is load-bearing (a stale-thinking-pill / request-error
// masking class of bugs exists in history): outcome/run-state mapping FIRST,
// then terminal-signal state (terminal agents), then no-environment, then
// blocked-on-input -> READY/WAITING, then request-error.
//
// `status` walks the RAW agent-message log (the same dict shape the message
// fold consumes — `agent_message.message`), NOT the folded ChatMessage[]; the
// Python property walks `self._messages` (the raw Message objects). The stored
// `agent.run_state` (lifecycle) maps onto the Python `Task.outcome`
// (`TaskState`), whose value set is identical to `RunState`.

import type { RunState } from "~/db/schema/enums";
import type { RawMessage } from "~/projection/message_log";
import { objectType } from "~/projection/message_log";
import type { TaskStatus } from "~/projection/view_types";

// Terminal-agent status vocabulary. Mirrors `TerminalStatusSignal` in
// interfaces/agents/agent.py.
export type TerminalStatusSignal = "BUSY" | "IDLE" | "WAITING";

// --- Harness tool-name classification (Claude Code harness) ---------------
//
// Mirrors `is_ask_user_question_tool` / `is_exit_plan_mode_tool` /
// `is_valid_ask_user_question_input` in
// `sculptor/sculptor/agents/default/claude_code_sdk/harness.py`. The status
// derivation only ever runs against the Claude harness in this rewrite, so the
// name sets are inlined (as in message_conversion.ts).

const MCP_ASK_USER_QUESTION_TOOL_NAME = "mcp__sculptor__ask_user_question";
const ASK_USER_QUESTION_TOOL_NAMES = new Set<string>([
  "AskUserQuestion",
  MCP_ASK_USER_QUESTION_TOOL_NAME,
]);
const EXIT_PLAN_MODE_TOOL_NAMES = new Set<string>([
  "ExitPlanMode",
  "mcp__sculptor__exit_plan_mode",
]);

function isAskUserQuestionTool(name: string): boolean {
  return ASK_USER_QUESTION_TOOL_NAMES.has(name);
}

function isExitPlanModeTool(name: string): boolean {
  return EXIT_PLAN_MODE_TOOL_NAMES.has(name);
}

// Port of `is_valid_ask_user_question_input`: only the MCP-FQN tool name is
// strictly validated; the legacy built-in `AskUserQuestion` always passes.
// Strict validation requires `questions` to be a list whose entries each parse
// as a `UserQuestion` (question/header: str; options: list of {label,
// description: str}; multi_select: bool; optional other_label: str|null).
function isValidAskUserQuestionInput(name: string, input: Record<string, unknown>): boolean {
  if (name !== MCP_ASK_USER_QUESTION_TOOL_NAME) {
    return true;
  }
  const questions = input["questions"];
  if (!Array.isArray(questions)) {
    return false;
  }
  return questions.every(isValidUserQuestion);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isValidUserQuestion(value: unknown): boolean {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const q = value as Record<string, unknown>;
  if (!isString(q["question"]) || !isString(q["header"])) {
    return false;
  }
  if (!Array.isArray(q["options"])) {
    return false;
  }
  for (const option of q["options"]) {
    if (typeof option !== "object" || option === null) {
      return false;
    }
    const o = option as Record<string, unknown>;
    if (!isString(o["label"]) || !isString(o["description"])) {
      return false;
    }
  }
  if (typeof q["multi_select"] !== "boolean") {
    return false;
  }
  if (q["other_label"] !== undefined && q["other_label"] !== null && !isString(q["other_label"])) {
    return false;
  }
  return true;
}

// --- Raw message field access ---------------------------------------------

function toolUseBlocksOf(message: RawMessage): { name: string; input: Record<string, unknown> }[] {
  const content = message["content"];
  if (!Array.isArray(content)) {
    return [];
  }
  const blocks: { name: string; input: Record<string, unknown> }[] = [];
  for (const block of content) {
    if (
      typeof block === "object" &&
      block !== null &&
      (block as Record<string, unknown>)["object_type"] === "ToolUseBlock"
    ) {
      const b = block as Record<string, unknown>;
      blocks.push({
        name: b["name"] as string,
        input: (b["input"] ?? {}) as Record<string, unknown>,
      });
    }
  }
  return blocks;
}

// --- scan_terminal_signal_state -------------------------------------------

// (run_started, latest_signal_this_run) from a terminal task's live messages.
// Faithful port of `scan_terminal_signal_state`: scanned in reverse, the latest
// signal wins but only if it arrived after the most recent run start
// (EnvironmentAcquired anchor); an EnvironmentReleased seen first means the run
// ended and its signals are stale; no anchor at all means the run hasn't
// started.
export function scanTerminalSignalState(
  messages: readonly RawMessage[],
): { runStarted: boolean; latestSignal: TerminalStatusSignal | null } {
  let latestSignal: TerminalStatusSignal | null = null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined) {
      continue;
    }
    const type = objectType(message);
    if (latestSignal === null && type === "TerminalAgentSignalRunnerMessage") {
      latestSignal = message["signal"] as TerminalStatusSignal;
    }
    if (type === "EnvironmentReleasedRunnerMessage") {
      return { runStarted: false, latestSignal: null };
    }
    if (type === "EnvironmentAcquiredRunnerMessage") {
      return { runStarted: true, latestSignal };
    }
  }
  return { runStarted: false, latestSignal: null };
}

// --- _maybe_get_status_from_outcome ---------------------------------------

// Port of `_maybe_get_status_from_outcome`. `hasState` is whether the agent has
// a persisted state (Python's `task_state is None`); on this rewrite the agent
// row IS its current state, so a coding agent always has state (true). The
// branch is preserved for fidelity.
function maybeGetStatusFromOutcome(runState: RunState, hasState: boolean): TaskStatus | null {
  if (runState === "FAILED") {
    return "ERROR";
  }
  if (runState === "QUEUED") {
    return "BUILDING";
  }
  if (runState === "SUCCEEDED" || runState === "CANCELLED" || runState === "DELETED") {
    return "READY";
  }
  // Otherwise the task is running.
  if (!hasState) {
    return "BUILDING";
  }
  return null;
}

// --- _ready_or_waiting ----------------------------------------------------

// Port of `CodingAgentTaskView._ready_or_waiting`: WAITING if the agent has an
// unanswered AskUserQuestion / ExitPlanMode whose surrounding request has not
// since completed, else READY. Walks messages in reverse; a
// UserQuestionAnswerMessage or a PersistentRequestComplete (Success / Failure /
// Stopped / Skipped) older than the AUQ ends the search (the turn has settled).
function readyOrWaiting(messages: readonly RawMessage[]): TaskStatus {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined) {
      continue;
    }
    const type = objectType(message);
    if (type === "UserQuestionAnswerMessage") {
      break;
    }
    if (isPersistentRequestComplete(type)) {
      break;
    }
    if (type === "AskUserQuestionAgentMessage") {
      return "WAITING";
    }
    if (type === "ResponseBlockAgentMessage") {
      for (const block of toolUseBlocksOf(message)) {
        if (isAskUserQuestionTool(block.name) && isValidAskUserQuestionInput(block.name, block.input)) {
          return "WAITING";
        }
        if (isExitPlanModeTool(block.name)) {
          return "WAITING";
        }
      }
    }
  }
  return "READY";
}

// The PersistentRequestCompleteAgentMessage subclasses (interfaces/agents/agent.py):
// RequestSuccess / RequestFailure / RequestStopped / RequestSkipped.
const PERSISTENT_REQUEST_COMPLETE_TYPES = new Set<string>([
  "RequestSuccessAgentMessage",
  "RequestFailureAgentMessage",
  "RequestStoppedAgentMessage",
  "RequestSkippedAgentMessage",
]);

function isPersistentRequestComplete(type: string): boolean {
  return PERSISTENT_REQUEST_COMPLETE_TYPES.has(type);
}

// Port of `_last_request_failed`: true if the most recent completed request
// ended with a RequestFailure.
function lastRequestFailed(messages: readonly RawMessage[]): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined) {
      continue;
    }
    const type = objectType(message);
    if (isPersistentRequestComplete(type)) {
      return type === "RequestFailureAgentMessage";
    }
  }
  return false;
}

// --- status ---------------------------------------------------------------

// Faithful port of `CodingAgentTaskView.status`. `isTerminalAgent` mirrors
// `is_terminal_agent_config(self.task_input.agent_config)`. `hasState` mirrors
// `self.task_state is not None` (always true for a coding agent on this rewrite).
export function computeStatus(
  runState: RunState,
  isTerminalAgent: boolean,
  messages: readonly RawMessage[],
  hasState: boolean,
): TaskStatus {
  const fromOutcome = maybeGetStatusFromOutcome(runState, hasState);
  if (fromOutcome !== null) {
    return fromOutcome;
  }

  if (isTerminalAgent) {
    // Terminal agents have no chat: status comes from the latest signal posted
    // since the most recent run start. No run-start anchor -> still building.
    const { runStarted, latestSignal } = scanTerminalSignalState(messages);
    if (!runStarted) {
      return "BUILDING";
    }
    if (latestSignal === "BUSY") {
      return "RUNNING";
    }
    if (latestSignal === "WAITING") {
      return "WAITING";
    }
    return "READY";
  }

  // Has the environment been acquired via message?
  const hasEnvironment = messages.some((m) => objectType(m) === "EnvironmentAcquiredRunnerMessage");
  if (!hasEnvironment) {
    // Prompt-less creation: no user message yet -> READY so the user can type.
    const hasUserMessage = messages.some((m) => objectType(m) === "ChatInputUserMessage");
    if (!hasUserMessage) {
      return "READY";
    }
    return "BUILDING";
  }

  const chatInputMessageIds: string[] = [];
  for (const message of messages) {
    const type = objectType(message);
    if (type === "ChatInputUserMessage" || type === "UserQuestionAnswerMessage") {
      chatInputMessageIds.push(message["message_id"] as string);
    }
  }
  const requestFinishedIds = new Set<string>();
  for (const message of messages) {
    if (objectType(message) === "RequestSuccessAgentMessage" ||
      objectType(message) === "RequestFailureAgentMessage" ||
      objectType(message) === "RequestStoppedAgentMessage" ||
      objectType(message) === "RequestSkippedAgentMessage"
    ) {
      requestFinishedIds.add(message["request_id"] as string);
    }
  }

  // An unanswered AskUserQuestion / ExitPlanMode pins WAITING regardless of
  // whether the in-flight request has formally completed (held MCP tools/call).
  const status = readyOrWaiting(messages);
  if (status === "WAITING") {
    return "WAITING";
  }

  const isReady = chatInputMessageIds.every((id) => requestFinishedIds.has(id));
  if (isReady) {
    if (lastRequestFailed(messages)) {
      return "REQUEST_ERROR";
    }
    return status;
  }
  return "RUNNING";
}
