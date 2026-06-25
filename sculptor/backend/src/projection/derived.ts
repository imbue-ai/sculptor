// Computes the derived, UI-facing per-agent view (`CodingAgentTaskView`).
//
// Ported from `sculptor/sculptor/web/derived.py` — the `CodingAgentTaskView`
// computed fields owned by Task 4.3: the derived `status`, `title`, `goal`,
// activity description (`current_activity` / `last_activity`), the latest v2
// TaskListArtifact progress (`task_completed` / `task_total` /
// `current_task_subject`), and the WAITING / ERROR detail strings. Ports the
// helpers `_describe_tool_use`, `_get_last_task_list_artifact`,
// `_find_latest_activity`, `_FRIENDLY_ERROR_NAMES`, and the AUQ/plan-approval
// `waiting_detail` walk.
//
// The view is computed from the RAW agent-message log (the same dict shape the
// message fold consumes), mirroring how the Python property walks
// `self._messages`. `status` itself lives in status.ts.

import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { AgentRow } from "~/db/schema/agent";
import type { RawMessage } from "~/projection/message_log";
import { objectType } from "~/projection/message_log";
import { computeStatus } from "~/projection/status";
import type {
  CodingAgentTaskView,
  HarnessCapabilities,
  ModelOption,
  TaskInterface,
  TaskState,
  TaskStatus,
  WorkspacePeekAgentStatus,
} from "~/projection/view_types";

// The terminal-agent config discriminators (interfaces/agents/agent.py
// `TERMINAL_AGENT_CONFIG_TYPES`).
const TERMINAL_AGENT_CONFIG_TYPES = new Set<string>([
  "TerminalAgentConfig",
  "RegisteredTerminalAgentConfig",
]);

function isTerminalAgentConfig(agentConfig: Record<string, unknown>): boolean {
  return TERMINAL_AGENT_CONFIG_TYPES.has(agentConfig["object_type"] as string);
}

// --- Tool-use activity description ----------------------------------------
//
// Port of `_TOOL_DESCRIPTIONS` / `_describe_tool_use`. (active, past, uses_file_path)
const TOOL_DESCRIPTIONS: Record<string, [string, string, boolean]> = {
  Edit: ["Editing", "Edited", true],
  Read: ["Reading", "Read", true],
  Write: ["Creating", "Created", true],
  Bash: ["Running command", "Ran command", false],
  Grep: ["Searching codebase", "Searched codebase", false],
  Glob: ["Finding files", "Found files", false],
  Task: ["Running sub-agent", "Ran sub-agent", false],
};

function describeToolUse(
  block: { name: string; input: Record<string, unknown> },
  pastTense: boolean,
): string {
  const entry = TOOL_DESCRIPTIONS[block.name];
  if (entry === undefined) {
    return block.name;
  }
  const [active, past, usesFilePath] = entry;
  const verb = pastTense ? past : active;
  if (usesFilePath) {
    const filePath = block.input["file_path"];
    const shortPath =
      typeof filePath === "string" && filePath ? (filePath.split("/").pop() ?? null) : null;
    return shortPath ? `${verb} ${shortPath}` : `${verb} file`;
  }
  return verb;
}

// Maps raw exception class names to user-friendly messages
// (`_FRIENDLY_ERROR_NAMES`).
const FRIENDLY_ERROR_NAMES: Record<string, string> = {
  KeyboardInterrupt: "Agent stopped unexpectedly",
  SystemExit: "Agent stopped unexpectedly",
};

// --- Block helpers --------------------------------------------------------

interface ContentBlockRaw {
  object_type?: string;
  name?: string;
  input?: Record<string, unknown>;
  text?: string;
}

function rawBlocks(message: RawMessage): ContentBlockRaw[] {
  const content = message["content"];
  return Array.isArray(content) ? (content as ContentBlockRaw[]) : [];
}

// --- _find_latest_activity ------------------------------------------------

function findLatestActivity(messages: readonly RawMessage[], pastTense: boolean): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined || objectType(message) !== "ResponseBlockAgentMessage") {
      continue;
    }
    const blocks = rawBlocks(message);
    for (let j = blocks.length - 1; j >= 0; j--) {
      const block = blocks[j];
      if (block === undefined) {
        continue;
      }
      if (block.object_type === "ToolUseBlock") {
        return describeToolUse({ name: block.name ?? "", input: block.input ?? {} }, pastTense);
      }
      if (block.object_type === "TextBlock" && (block.text ?? "").trim()) {
        return pastTense ? "Responded" : "Responding";
      }
    }
  }
  return null;
}

// --- _get_last_task_list_artifact -----------------------------------------

interface TaskListArtifact {
  tasks: { subject: string; status: string }[];
}

// Port of `_get_last_task_list_artifact`: walk backwards for an
// UpdatedArtifactAgentMessage whose artifact.name == PLAN, then read + parse the
// on-disk v2 TaskListArtifact file. Legacy / version != 2 / unreadable files are
// skipped so older artifacts don't masquerade as fresh ones.
function getLastTaskListArtifact(messages: readonly RawMessage[]): TaskListArtifact | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined || objectType(message) !== "UpdatedArtifactAgentMessage") {
      continue;
    }
    const artifact = message["artifact"] as Record<string, unknown> | undefined;
    if (artifact === undefined || artifact["name"] !== "PLAN") {
      continue;
    }
    const urlStr = String(artifact["url"] ?? "");
    if (!urlStr.startsWith("file://")) {
      return null;
    }
    const path = fileURLToPath(urlStr);
    if (!existsSync(path)) {
      continue;
    }
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
    } catch {
      continue;
    }
    if (data["object_type"] !== "TaskListArtifact" || data["version"] !== 2) {
      continue;
    }
    const tasks = data["tasks"];
    if (!Array.isArray(tasks)) {
      continue;
    }
    return {
      tasks: tasks.map((t) => {
        const task = t as Record<string, unknown>;
        return { subject: task["subject"] as string, status: task["status"] as string };
      }),
    };
  }
  return null;
}

// --- goal / title ---------------------------------------------------------

function computeGoal(messages: readonly RawMessage[]): string {
  for (const message of messages) {
    if (objectType(message) === "ChatInputUserMessage") {
      return (message["text"] as string) ?? "";
    }
  }
  return "";
}

// --- waiting_detail -------------------------------------------------------

// Port of `CodingAgentTaskView.waiting_detail` (only meaningful when WAITING).
function computeWaitingDetail(messages: readonly RawMessage[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined) {
      continue;
    }
    const type = objectType(message);
    if (type === "UserQuestionAnswerMessage") {
      break;
    }
    if (type === "AskUserQuestionAgentMessage") {
      const questionData = message["question_data"] as Record<string, unknown> | undefined;
      const questions = (questionData?.["questions"] as Record<string, unknown>[] | undefined) ?? [];
      if (questions.length > 0 && questions[0]?.["header"] === "Plan approval") {
        return "Waiting for plan approval";
      }
      if (questions.length > 0) {
        return (questions[0]?.["question"] as string) ?? null;
      }
      return null;
    }
    if (type === "ResponseBlockAgentMessage") {
      for (const block of rawBlocks(message)) {
        if (block.object_type === "ToolUseBlock" && isExitPlanModeToolName(block.name ?? "")) {
          return "Waiting for plan approval";
        }
      }
    }
  }
  return null;
}

const EXIT_PLAN_MODE_TOOL_NAMES = new Set<string>(["ExitPlanMode", "mcp__sculptor__exit_plan_mode"]);

function isExitPlanModeToolName(name: string): boolean {
  return EXIT_PLAN_MODE_TOOL_NAMES.has(name);
}

// --- error_detail ---------------------------------------------------------

interface SerializedError {
  exception: string;
  args: unknown[];
}

function readError(value: unknown): SerializedError | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const error = value as Record<string, unknown>;
  return {
    exception: (error["exception"] as string) ?? "",
    args: Array.isArray(error["args"]) ? (error["args"] as unknown[]) : [],
  };
}

// Port of `CodingAgentTaskView.error_detail`. For REQUEST_ERROR, surface the
// most recent RequestFailure's error; for ERROR, surface the agent's persisted
// error (with the friendly-name mapping). Null otherwise.
function computeErrorDetail(
  status: TaskStatus,
  messages: readonly RawMessage[],
  agentError: unknown,
): string | null {
  if (status === "REQUEST_ERROR") {
    for (let i = messages.length - 1; i >= 0; i--) {
      const message = messages[i];
      if (message === undefined || objectType(message) !== "RequestFailureAgentMessage") {
        continue;
      }
      const error = readError(message["error"]);
      if (error === null) {
        return null;
      }
      if (error.args.length > 0 && typeof error.args[0] === "string") {
        return error.args[0];
      }
      return error.exception;
    }
    return null;
  }
  if (status !== "ERROR") {
    return null;
  }
  const error = readError(agentError);
  if (error === null) {
    return null;
  }
  if (error.args.length > 0 && typeof error.args[0] === "string") {
    return error.args[0];
  }
  return FRIENDLY_ERROR_NAMES[error.exception] ?? error.exception;
}

// --- Harness identity (capabilities / model switcher) ---------------------
//
// Ported from each harness's `capabilities()` (claude/pi/terminal/hello). The
// view resolves these by the agent config's harness kind without instantiating a
// harness (the registry's runtime deps aren't available in the projection).

function harnessKindForView(
  agentConfig: Record<string, unknown>,
): "claude" | "pi" | "hello" | "terminal" {
  switch (agentConfig["object_type"]) {
    case "PiAgentConfig":
      return "pi";
    case "HelloAgentConfig":
      return "hello";
    case "TerminalAgentConfig":
    case "RegisteredTerminalAgentConfig":
      return "terminal";
    default:
      return "claude";
  }
}

function capabilities(flags: Partial<HarnessCapabilities>): HarnessCapabilities {
  return {
    supports_chat_interface: false,
    supports_interactive_backchannel: false,
    supports_skills: false,
    supports_sub_agents: false,
    supports_image_input: false,
    supports_fast_mode: false,
    supports_context_reset: false,
    supports_compaction: false,
    supports_background_tasks: false,
    supports_session_resume: false,
    supports_tool_use_rendering: false,
    supports_file_attachments: false,
    supports_interruption: false,
    supports_file_references: false,
    supports_model_selection: false,
    ...flags,
  };
}

const ALL_CAPABILITIES_TRUE: HarnessCapabilities = capabilities({
  supports_chat_interface: true,
  supports_interactive_backchannel: true,
  supports_skills: true,
  supports_sub_agents: true,
  supports_image_input: true,
  supports_fast_mode: true,
  supports_context_reset: true,
  supports_compaction: true,
  supports_background_tasks: true,
  supports_session_resume: true,
  supports_tool_use_rendering: true,
  supports_file_attachments: true,
  supports_interruption: true,
  supports_file_references: true,
  supports_model_selection: true,
});

function harnessCapabilities(
  kind: "claude" | "pi" | "hello" | "terminal",
): HarnessCapabilities {
  switch (kind) {
    case "claude":
      return ALL_CAPABILITIES_TRUE;
    case "pi":
      // pi mirrors claude except fast mode (pi_agent/harness.py).
      return capabilities({ ...ALL_CAPABILITIES_TRUE, supports_fast_mode: false });
    case "hello":
      return capabilities({ supports_chat_interface: true });
    case "terminal":
      // Terminal agents have no chat stream — uniformly false.
      return capabilities({});
  }
}

// The LLMModel wire values that support smooth (partial-message) streaming
// (`CodingAgentTaskView.is_smooth_streaming_supported`). Every current Claude /
// fake model qualifies.
const SMOOTH_STREAMING_MODELS: ReadonlySet<string> = new Set([
  "CLAUDE-4-OPUS",
  "CLAUDE-4-OPUS-200K",
  "CLAUDE-4-7-OPUS",
  "CLAUDE-4-7-OPUS-200K",
  "CLAUDE-4-6-OPUS",
  "CLAUDE-4-6-OPUS-200K",
  "CLAUDE-4-SONNET",
  "CLAUDE-4-SONNET-200K",
  "CLAUDE-4-HAIKU",
  "CLAUDE-FABLE-5",
  "FAKE_CLAUDE",
  "FAKE_CLAUDE_2",
]);

// The model wire value the switcher reflects: the most recent user message that
// carried an explicit selection, then the creation default, then CLAUDE-FABLE-5
// (CodingAgentTaskView.model).
const DEFAULT_MODEL = "CLAUDE-FABLE-5";

function resolveModel(agent: AgentRow, messages: readonly RawMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message === undefined) {
      continue;
    }
    if (objectType(message) === "ChatInputUserMessage") {
      const modelName = (message as Record<string, unknown>)["model_name"];
      if (typeof modelName === "string" && modelName !== "") {
        return modelName;
      }
    }
  }
  return agent.defaultModel ?? DEFAULT_MODEL;
}

// `updated_at`: the latest user-visible content message time, else created_at
// (derived.py `updated_at`). Content excludes user messages and request
// lifecycle bookkeeping (ephemeral messages are not persisted into the log).
const NON_CONTENT_MESSAGE_TYPES: ReadonlySet<string> = new Set([
  "RequestStartedAgentMessage",
  "PersistentRequestCompleteAgentMessage",
  "RemoveQueuedMessageAgentMessage",
  "RequestSuccessAgentMessage",
  "RequestFailureAgentMessage",
  "RequestStoppedAgentMessage",
  "RequestSkippedAgentMessage",
]);

function isContentMessage(message: RawMessage): boolean {
  const record = message as Record<string, unknown>;
  if (record["source"] === "USER") {
    return false;
  }
  return !NON_CONTENT_MESSAGE_TYPES.has(objectType(message) ?? "");
}

function resolveUpdatedAt(agent: AgentRow, messages: readonly RawMessage[]): string {
  if (messages.length === 0) {
    return agent.createdAt;
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message !== undefined && isContentMessage(message)) {
      const time = (message as Record<string, unknown>)["approximate_creation_time"];
      if (typeof time === "string") {
        return time;
      }
    }
  }
  const first = messages[0] as Record<string, unknown> | undefined;
  const firstTime = first?.["approximate_creation_time"];
  return typeof firstTime === "string" ? firstTime : agent.createdAt;
}

function resolveAutoCompacting(messages: readonly RawMessage[]): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    const type = objectType(messages[i] as RawMessage);
    if (type === "AutoCompactingDoneAgentMessage") {
      return false;
    }
    if (type === "AutoCompactingAgentMessage") {
      return true;
    }
  }
  return false;
}

function resolveArtifactNames(messages: readonly RawMessage[]): string[] {
  const names = new Set<string>();
  for (const message of messages) {
    if (objectType(message) === "UpdatedArtifactAgentMessage") {
      const artifact = (message as Record<string, unknown>)["artifact"];
      const name = (artifact as Record<string, unknown> | undefined)?.["name"];
      if (typeof name === "string") {
        names.add(name);
      }
    }
  }
  return [...names];
}

// Maps the derived UI status to the workspace-tab peek status, with SUCCEEDED
// run_state overriding to COMPLETED (derived.py `_compute_workspace_peek_status`).
function workspacePeekStatus(
  runState: TaskState,
  status: TaskStatus,
): WorkspacePeekAgentStatus {
  if (runState === "SUCCEEDED") {
    return "COMPLETED";
  }
  switch (status) {
    case "BUILDING":
    case "RUNNING":
      return "WORKING";
    case "WAITING":
      return "WAITING";
    case "ERROR":
    case "REQUEST_ERROR":
      return "ERROR";
    case "READY":
      return "IDLE";
  }
}

// --- computeAgentView -----------------------------------------------------

// Compute the derived per-agent view from the agent row + its raw message log.
// `messages` are the raw `agent_message.message` dicts in log order.
export function computeAgentView(agent: AgentRow, messages: readonly RawMessage[]): CodingAgentTaskView {
  const isTerminal = isTerminalAgentConfig(agent.agentConfig);
  // On this rewrite the agent row IS its current state, so a coding agent
  // always "has state" (Python's `task_state is not None`).
  const status = computeStatus(agent.runState, isTerminal, messages, true);
  const artifact = getLastTaskListArtifact(messages);
  const kind = harnessKindForView(agent.agentConfig);
  const goal = computeGoal(messages);
  const title = agent.title ?? null;
  const model = resolveModel(agent, messages);
  const agentConfig = agent.agentConfig;
  const acceptsAutomatedPrompts =
    agentConfig["object_type"] === "RegisteredTerminalAgentConfig" &&
    agentConfig["accepts_automated_prompts"] === true;
  const availableModels: ModelOption[] =
    kind === "pi" && Array.isArray(agent.availableModels)
      ? (agent.availableModels as ModelOption[])
      : [];
  const selectedModelId =
    kind === "pi"
      ? ((agent.currentModel as ModelOption | null)?.model_id ?? null)
      : null;
  const taskInterface: TaskInterface = isTerminal ? "TERMINAL" : "API";

  return {
    object_type: "CodingAgentTaskView",
    id: agent.objectId,
    project_id: agent.projectId,
    workspace_id: agent.workspaceId ?? null,
    created_at: agent.createdAt,
    updated_at: resolveUpdatedAt(agent, messages),
    task_status: agent.runState as TaskState,
    title,
    title_or_something_like_it: title ?? goal,
    goal,
    initial_prompt: goal,
    interface: taskInterface,
    model,
    selected_model_id: selectedModelId,
    available_models: availableModels,
    harness_capabilities: harnessCapabilities(kind),
    accepts_automated_prompts: acceptsAutomatedPrompts,
    is_smooth_streaming_supported: SMOOTH_STREAMING_MODELS.has(model),
    is_auto_compacting: resolveAutoCompacting(messages),
    artifact_names: resolveArtifactNames(messages),
    is_deleted: agent.isDeleted || agent.isDeleting,
    last_read_at: agent.lastReadAt ?? null,
    workspace_peek_status: workspacePeekStatus(agent.runState as TaskState, status),
    status,
    current_activity: findLatestActivity(messages, false),
    last_activity: findLatestActivity(messages, true),
    task_completed: artifact === null ? 0 : artifact.tasks.filter((t) => t.status === "completed").length,
    task_total: artifact === null ? 0 : artifact.tasks.length,
    current_task_subject:
      artifact === null
        ? null
        : (artifact.tasks.find((t) => t.status === "in_progress")?.subject ?? null),
    waiting_detail: status === "WAITING" ? computeWaitingDetail(messages) : null,
    error_detail: computeErrorDetail(status, messages, agent.error),
  };
}
