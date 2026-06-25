import { existsSync, readdirSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { z } from "zod";

import { getOrm } from "~/db/orm";
import {
  appendAgentMessage,
  createAgent,
  findAgentsByPrefix,
  getAgent,
  getWorkspace,
  listAgentsByWorkspace,
  setAgentDeleting,
  setAgentRunState,
  softDeleteAgent,
  updateAgent,
} from "~/db/repositories";
import { eventBus } from "~/events";
import type { AgentRow } from "~/db/schema";
import { artifactsPath, statePath, workingDirectory } from "~/environment/paths";
import { revParseHead } from "~/git";
import {
  SESSION_ID_STATE_FILE_NAME,
  VALIDATED_SESSION_ID_STATE_FILE_NAME,
} from "~/harness/claude/constants";
import { resolveJsonlDirectory } from "~/harness/claude/paths";
import { PI_SESSION_ID_STATE_FILE } from "~/harness/pi/launch";
import { newAgentId, newAgentMessageId } from "~/ids";
import { projectionCache } from "~/projection/cache";
import { computeAgentView } from "~/projection/derived";
import { camelizeDeep } from "~/projection/to_wire";
import { getRegistration } from "~/services/terminal_agent_registry/registry";
import { getRepo } from "~/db/repositories";
import { localPathFromRepo } from "~/services/project";
import { getAgentRunner } from "~/runner/instance";

// Agent (internally was "Task") lifecycle service (web/app.py). Create persists
// an `agent` row, the optional first user message, and starts a supervisor via
// the wired runner (Task 6.7 part 1). The wire keeps the camelCase
// CodingAgentTaskView (a subset in the rewrite — the model-switcher / harness
// capability fields are computed elsewhere).

export class AgentError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export type AgentTypeName = "claude" | "pi" | "terminal" | "registered";

// The full camelCase CodingAgentTaskView wire shape (RW-API-3). It is the
// camelization of the internal snake-case view, identical to the stream's
// task_views entries (to_wire.ts), so REST and stream agree byte-for-byte. The
// schema is the single source of truth shared with the agent routes (so the
// response serializer emits every field and the OpenAPI overlay's shape holds).
const HarnessCapabilitiesSchema = z.object({
  supportsChatInterface: z.boolean(),
  supportsInteractiveBackchannel: z.boolean(),
  supportsSkills: z.boolean(),
  supportsSubAgents: z.boolean(),
  supportsImageInput: z.boolean(),
  supportsFastMode: z.boolean(),
  supportsContextReset: z.boolean(),
  supportsCompaction: z.boolean(),
  supportsBackgroundTasks: z.boolean(),
  supportsSessionResume: z.boolean(),
  supportsToolUseRendering: z.boolean(),
  supportsFileAttachments: z.boolean(),
  supportsInterruption: z.boolean(),
  supportsFileReferences: z.boolean(),
  supportsModelSelection: z.boolean(),
});

const ModelOptionSchema = z.object({
  provider: z.string(),
  modelId: z.string(),
  displayName: z.string(),
});

export const AgentViewSchema = z.object({
  objectType: z.literal("CodingAgentTaskView"),
  id: z.string(),
  projectId: z.string(),
  workspaceId: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
  taskStatus: z.string(),
  title: z.string().nullable(),
  titleOrSomethingLikeIt: z.string(),
  goal: z.string(),
  initialPrompt: z.string(),
  interface: z.string(),
  model: z.string(),
  selectedModelId: z.string().nullable(),
  availableModels: z.array(ModelOptionSchema),
  harnessCapabilities: HarnessCapabilitiesSchema,
  acceptsAutomatedPrompts: z.boolean(),
  isSmoothStreamingSupported: z.boolean(),
  isAutoCompacting: z.boolean(),
  artifactNames: z.array(z.string()),
  isDeleted: z.boolean(),
  lastReadAt: z.string().nullable(),
  workspacePeekStatus: z.string(),
  status: z.string(),
  currentActivity: z.string().nullable(),
  lastActivity: z.string().nullable(),
  taskCompleted: z.number().int(),
  taskTotal: z.number().int(),
  currentTaskSubject: z.string().nullable(),
  waitingDetail: z.string().nullable(),
  errorDetail: z.string().nullable(),
});

export type AgentViewWire = z.infer<typeof AgentViewSchema>;

// Build the wire view from the warm projection cache (Task 4.3 + the full view
// fields). camelizeDeep matches the /stream/ws task-view serialization exactly.
export function agentViewWire(agent: AgentRow): AgentViewWire {
  const view = projectionCache.ensure(getOrm(), agent.objectId)?.view;
  if (view === undefined) {
    return camelizeDeep(computeAgentView(agent, [])) as AgentViewWire;
  }
  return camelizeDeep(view) as AgentViewWire;
}

// Record a user-authored message (chat input, question answer): persist it,
// fold it into the warm cache, and publish it on the stream — the same three
// effects the supervisor's MessageWriter applies to harness messages. Without
// the cache/stream steps the message is persisted but never reaches a live
// client (the warm cache was folded at connect, before the message existed), so
// the user's own message silently vanishes until a reconnect re-folds from disk.
function recordUserMessage(
  orm: ReturnType<typeof getOrm>,
  agent: AgentRow,
  message: Record<string, unknown>,
): void {
  appendAgentMessage(orm, agent.objectId, message);
  projectionCache.applyMessage(orm, agent.objectId, message);
  eventBus.publish({
    kind: "agent_message",
    agentId: agent.objectId,
    workspaceId: agent.workspaceId ?? undefined,
    projectId: agent.projectId,
    message,
  });
}

export interface CreateAgentInput {
  prompt?: string | null;
  model?: string | null;
  files?: string[];
  name?: string | null;
  enterPlanMode?: boolean;
  fastMode?: boolean;
  effort?: string;
  sentVia?: string | null;
  agentType?: AgentTypeName;
  registrationId?: string | null;
}

// Resolve the requested agent type into a stamped agent_config + its default-name
// prefix. Ports `_agent_config_for_request` (web/app.py): registered terminal
// agents look up their registration so the config stays self-describing and the
// tab names from the registration's display name.
function resolveAgentConfig(
  agentType: AgentTypeName,
  registrationId: string | null,
): { config: Record<string, unknown>; namePrefix: string } {
  switch (agentType) {
    case "terminal":
      return { config: { object_type: "TerminalAgentConfig" }, namePrefix: "Terminal" };
    case "pi":
      return { config: { object_type: "PiAgentConfig" }, namePrefix: "Pi" };
    case "registered": {
      if (registrationId === null || registrationId === "") {
        throw new AgentError(422, "registered terminal agents require a registration_id");
      }
      const registration = getRegistration(registrationId);
      if (registration === null) {
        throw new AgentError(
          422,
          `Terminal-agent registration '${registrationId}' not found`,
        );
      }
      return {
        config: {
          object_type: "RegisteredTerminalAgentConfig",
          registration_id: registration.registrationId,
          display_name: registration.displayName,
          launch_command: registration.launchCommand,
          resume_command_template: registration.resumeCommandTemplate,
          accepts_automated_prompts: registration.acceptsAutomatedPrompts,
        },
        namePrefix: registration.displayName,
      };
    }
    default:
      return { config: { object_type: "ClaudeCodeSDKAgentConfig" }, namePrefix: "Claude" };
  }
}

// Compute the next auto-generated agent name like "Claude N", reusing the lowest
// available number so deleting "Claude 1" frees it for the next agent. Numbering
// is independent per prefix. Ports app.py `_compute_next_agent_name`.
function computeNextAgentName(
  orm: ReturnType<typeof getOrm>,
  workspaceId: string,
  prefix: string,
): string {
  const pattern = new RegExp(
    `^${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} (\\d+)$`,
  );
  const used = new Set<number>();
  for (const agent of listAgentsByWorkspace(orm, workspaceId)) {
    if (agent.isDeleted) {
      continue;
    }
    const match = agent.title === null ? null : pattern.exec(agent.title);
    if (match) {
      used.add(Number(match[1]));
    }
  }
  let n = 1;
  while (used.has(n)) {
    n += 1;
  }
  return `${prefix} ${n}`;
}

function workspaceWorkingDir(
  workspace: ReturnType<typeof getWorkspace>,
): string {
  if (workspace === undefined || workspace.environmentId === null) {
    return "";
  }
  const repo = getRepo(getOrm(), workspace.projectId);
  const repoHostPath =
    repo !== undefined ? (localPathFromRepo(repo) ?? undefined) : undefined;
  return workingDirectory(
    workspace.environmentId,
    workspace.initializationStrategy,
    repoHostPath,
  );
}

export class AgentService {
  async create(
    workspaceId: string,
    input: CreateAgentInput,
  ): Promise<AgentViewWire> {
    const orm = getOrm();
    const workspace = getWorkspace(orm, workspaceId);
    if (workspace === undefined || workspace.isDeleted) {
      throw new AgentError(404, "Workspace not found");
    }
    const agentType = input.agentType ?? "claude";
    const prompt = input.prompt ?? null;
    if (
      prompt !== null &&
      prompt !== "" &&
      (input.model === null || input.model === undefined)
    ) {
      throw new AgentError(
        422,
        "A model is required when a prompt is provided",
      );
    }

    const repo = getRepo(orm, workspace.projectId);
    const workDir = workspaceWorkingDir(workspace);
    let startingGitHash: string | null = null;
    if (workDir !== "") {
      try {
        startingGitHash = await revParseHead(workDir);
      } catch {
        startingGitHash = null;
      }
    }

    const { config: agentConfig, namePrefix } = resolveAgentConfig(
      agentType,
      input.registrationId ?? null,
    );
    const agentId = newAgentId();
    const agent = createAgent(orm, {
      objectId: agentId,
      projectId: workspace.projectId,
      workspaceId,
      agentConfig,
      startingGitHash,
      systemPrompt: repo?.defaultSystemPrompt ?? null,
      defaultModel: input.model ?? null,
      title: input.name ?? computeNextAgentName(orm, workspaceId, namePrefix),
      runState: "QUEUED",
    });

    // Surface the freshly-created agent on the stream immediately (even before it
    // starts, e.g. a workspace's first agent created without a prompt), so the
    // client's task_views include it and can navigate to its chat. Without this
    // an agent that never starts (no prompt) would never reach the frontend.
    eventBus.publish({
      kind: "agent_status",
      agentId,
      workspaceId,
      projectId: workspace.projectId,
    });

    // Terminal agents have no harness turn: their "run" is the PTY the terminal
    // WebSocket spawns. Mark the run started and emit the EnvironmentAcquired
    // anchor so they leave BUILDING and the terminal-signal status scan (busy/
    // idle/waiting → dot) has a run to attach to.
    const configType = agentConfig.object_type;
    if (
      configType === "TerminalAgentConfig" ||
      configType === "RegisteredTerminalAgentConfig"
    ) {
      updateAgent(orm, agentId, { runState: "RUNNING" });
      recordUserMessage(orm, getAgent(orm, agentId) ?? agent, {
        object_type: "EnvironmentAcquiredRunnerMessage",
        message_id: newAgentMessageId(),
        source: "RUNNER",
        approximate_creation_time: new Date().toISOString(),
        environment: null,
      });
    }

    // A pi agent launches its harness on creation (even with no prompt) so the
    // pi process reports its model catalog and the switcher shows pi's models
    // immediately (run_agent/v1.py's start-time fetch_available_models_probe).
    if (configType === "PiAgentConfig") {
      getAgentRunner().startAgent(agentId);
    }

    if (prompt !== null && prompt !== "") {
      const message: Record<string, unknown> = {
        object_type: "ChatInputUserMessage",
        message_id: newAgentMessageId(),
        source: "USER",
        text: prompt,
        model_name: input.model ?? null,
        files: input.files ?? [],
        enter_plan_mode: input.enterPlanMode ?? false,
        fast_mode: input.fastMode ?? false,
        effort: input.effort ?? "xhigh",
        sent_via: input.sentVia ?? null,
        approximate_creation_time: new Date().toISOString(),
      };
      recordUserMessage(orm, agent, message);
      const runner = getAgentRunner();
      runner.startAgent(agentId);
      runner.sendUserMessage(agentId, message);
    }

    return agentViewWire(getAgent(orm, agentId) ?? agent);
  }

  list(workspaceId: string): AgentViewWire[] {
    const orm = getOrm();
    const workspace = getWorkspace(orm, workspaceId);
    if (workspace === undefined || workspace.isDeleted) {
      throw new AgentError(404, "Workspace not found");
    }
    return listAgentsByWorkspace(orm, workspaceId)
      .filter((agent) => !agent.isDeleted && !agent.isDeleting)
      .map((agent) => agentViewWire(agent));
  }

  resolveByPrefix(prefix: string): string {
    const orm = getOrm();
    const exact = getAgent(orm, prefix);
    if (exact !== undefined) {
      return exact.objectId;
    }
    const matches = findAgentsByPrefix(orm, prefix);
    if (matches.length === 0) {
      throw new AgentError(404, "No agent matches the prefix");
    }
    if (matches.length > 1) {
      throw new AgentError(409, "Multiple agents match the prefix");
    }
    return matches[0]!.objectId;
  }

  delete(agentId: string): void {
    const orm = getOrm();
    const agent = getAgent(orm, agentId);
    if (agent === undefined || agent.isDeleted) {
      throw new AgentError(404, "Agent not found");
    }
    if (agent.runState === "RUNNING") {
      // A running agent is flagged; the supervisor finalizes deletion on stop.
      setAgentDeleting(orm, agentId, true);
      getAgentRunner().stopAgent(agentId);
    }
    softDeleteAgent(orm, agentId);
  }

  // --- interaction (Task 6.8) ------------------------------------------------

  private requireAgent(agentId: string): AgentRow {
    const agent = getAgent(getOrm(), agentId);
    if (agent === undefined || agent.isDeleted) {
      throw new AgentError(404, "Agent not found");
    }
    return agent;
  }

  sendMessage(
    agentId: string,
    input: {
      message: string;
      model?: string | null;
      files?: string[];
      enterPlanMode?: boolean;
      exitPlanMode?: boolean;
      fastMode?: boolean;
      effort?: string;
      sentVia?: string | null;
    },
  ): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    // A pending AskUserQuestion must be answered (or dismissed) first; a plain
    // message would be ambiguous against the held tools/call (web/app.py L2166).
    if (projectionCache.ensure(orm, agentId)?.foldState.pendingUserQuestion != null) {
      throw new AgentError(
        409,
        "Cannot send a message while the agent is waiting for a response to AskUserQuestion.",
      );
    }
    const message: Record<string, unknown> = {
      object_type: "ChatInputUserMessage",
      message_id: newAgentMessageId(),
      source: "USER",
      text: input.message,
      model_name: input.model ?? null,
      files: input.files ?? [],
      enter_plan_mode: input.enterPlanMode ?? false,
      exit_plan_mode: input.exitPlanMode ?? false,
      fast_mode: input.fastMode ?? false,
      effort: input.effort ?? "xhigh",
      sent_via: input.sentVia ?? null,
      approximate_creation_time: new Date().toISOString(),
    };
    recordUserMessage(orm, agent, message);
    const runner = getAgentRunner();
    runner.startAgent(agentId);
    runner.sendUserMessage(agentId, message);
  }

  answerQuestion(
    agentId: string,
    input: {
      answers: Record<string, string>;
      notes: Record<string, string>;
      questionData: unknown;
      toolUseId: string;
    },
  ): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    const message: Record<string, unknown> = {
      object_type: "UserQuestionAnswerMessage",
      message_id: newAgentMessageId(),
      source: "USER",
      answers: input.answers,
      notes: input.notes,
      question_data: input.questionData,
      tool_use_id: input.toolUseId,
    };
    recordUserMessage(orm, agent, message);
    getAgentRunner().sendUserMessage(agentId, message);
  }

  // /clear — discard the model session (reset, not compaction) so the next turn
  // starts fresh (the CLI's --resume no longer fires).
  clearContext(agentId: string): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    // Reset the model session so the next turn starts fresh (no CLI --resume).
    // The harnesses resolve the session id from on-disk state files per turn
    // (claude session_id/validated_session_id, pi pi_session_id), so the row
    // columns alone don't reset it — delete the state files too.
    updateAgent(orm, agentId, { claudeSessionId: null, piSessionId: null });
    const root =
      agent.workspaceId === null
        ? undefined
        : getWorkspace(orm, agent.workspaceId)?.environmentId ?? undefined;
    if (root !== undefined) {
      const dir = statePath(root, agentId);
      for (const file of [
        SESSION_ID_STATE_FILE_NAME,
        VALIDATED_SESSION_ID_STATE_FILE_NAME,
        PI_SESSION_ID_STATE_FILE,
      ]) {
        rmSync(path.join(dir, file), { force: true });
      }
    }
    // A persistent harness process (pi) keeps the conversation in memory, so
    // also tell it to start a new session in-place.
    getAgentRunner().clearSession(agentId);
    // ...and record the cleared marker so the chat shows the context-reset
    // summary (web/app.py creates a ClearContextUserMessage whose harness reply
    // is this ContextClearedMessage; here we emit the visible result directly).
    recordUserMessage(orm, agent, {
      object_type: "ContextClearedMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      approximate_creation_time: new Date().toISOString(),
    });
  }

  interrupt(agentId: string): void {
    this.requireAgent(agentId);
    getAgentRunner().interruptAgent(agentId);
  }

  setModel(agentId: string, provider: string, modelId: string): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    updateAgent(orm, agentId, {
      currentModel: { provider, model_id: modelId },
    });
    eventBus.publish({
      kind: "agent_status",
      agentId,
      workspaceId: agent.workspaceId ?? undefined,
      projectId: agent.projectId,
    });
  }

  // A terminal-agent integration reported a status signal (busy/idle/waiting):
  // record it as a run-scoped runner message so the projection's
  // scanTerminalSignalState drives the derived status + dot. Ports app.py
  // post_agent_signal's status-event branch (TerminalAgentSignalRunnerMessage).
  recordTerminalSignal(
    agentId: string,
    signal: "BUSY" | "IDLE" | "WAITING",
  ): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    recordUserMessage(orm, agent, {
      object_type: "TerminalAgentSignalRunnerMessage",
      message_id: newAgentMessageId(),
      source: "RUNNER",
      approximate_creation_time: new Date().toISOString(),
      signal,
    });
  }

  // Remove a queued (not-yet-sent) message — e.g. the chat input's edit/delete
  // of a queued bar. Records a RemoveQueuedMessageAgentMessage tombstone (not a
  // hard delete) so the fold drops it from queued_chat_messages and the delta
  // streams the updated queue, without touching the busy turn's
  // current_request_id (web/app.py delete_workspace_agent_message →
  // RemoveQueuedMessageUserMessage → RemoveQueuedMessageAgentMessage).
  deleteMessage(agentId: string, messageId: string): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    recordUserMessage(orm, agent, {
      object_type: "RemoveQueuedMessageAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      removed_message_id: messageId,
      approximate_creation_time: new Date().toISOString(),
    });
  }

  restore(agentId: string): void {
    const orm = getOrm();
    const agent = getAgent(orm, agentId);
    if (agent === undefined || agent.isDeleted) {
      throw new AgentError(404, "Agent not found");
    }
    if (agent.runState !== "FAILED") {
      throw new AgentError(400, "Agent is not in a failed state");
    }
    setAgentRunState(orm, agentId, "QUEUED");
    getAgentRunner().startAgent(agentId);
  }

  diagnostics(agentId: string): {
    sessionId: string | null;
    transcriptFilePath: string | null;
    sculptorTranscriptFilePath: string | null;
  } {
    const orm = getOrm();
    const agent = getAgent(orm, agentId);
    if (agent === undefined || agent.isDeleted) {
      throw new AgentError(404, "Agent not found");
    }
    const workspace =
      agent.workspaceId === null
        ? undefined
        : getWorkspace(orm, agent.workspaceId);
    const root = workspace?.environmentId ?? null;
    const sessionId = agent.claudeSessionId ?? agent.piSessionId ?? null;
    // The CLI's own transcript: <jsonl-dir-for-cwd>/<session_id>.jsonl
    // (web/app.py get_jsonl_path_for_working_directory). Path is computed, not
    // existence-gated, mirroring the Python endpoint.
    let transcriptFilePath: string | null = null;
    if (sessionId !== null && agent.claudeSessionId !== null) {
      const workDir = workspaceWorkingDir(workspace);
      if (workDir !== "") {
        transcriptFilePath = path.join(
          resolveJsonlDirectory(os.homedir(), workDir),
          `${sessionId}.jsonl`,
        );
      }
    }
    // The Sculptor-side transcript artifact, only when it has been written
    // (app.py gates on .exists(), so the menu item disables until then).
    const sculptorTranscript =
      root === null ? null : path.join(artifactsPath(root, agentId), "transcript.jsonl");
    return {
      sessionId,
      transcriptFilePath,
      sculptorTranscriptFilePath:
        sculptorTranscript !== null && existsSync(sculptorTranscript)
          ? sculptorTranscript
          : null,
    };
  }

  artifact(agentId: string, artifactName: string): Record<string, unknown> {
    if (artifactName !== "DIFF" && artifactName !== "PLAN") {
      throw new AgentError(400, `Unknown artifact type: ${artifactName}`);
    }
    const orm = getOrm();
    const agent = getAgent(orm, agentId);
    if (agent === undefined || agent.isDeleted) {
      throw new AgentError(404, "Agent not found");
    }
    const workspace =
      agent.workspaceId === null
        ? undefined
        : getWorkspace(orm, agent.workspaceId);
    const root = workspace?.environmentId ?? null;
    if (root === null) {
      throw new AgentError(404, "Artifact not found");
    }
    const dir = artifactsPath(root, agentId);
    if (!existsSync(dir)) {
      throw new AgentError(404, "Artifact not found");
    }
    const match = readdirSync(dir).find((name) =>
      name.startsWith(`${artifactName}-`),
    );
    if (match === undefined) {
      throw new AgentError(404, "Artifact not found");
    }
    try {
      return JSON.parse(readFileSync(path.join(dir, match), "utf8")) as Record<
        string,
        unknown
      >;
    } catch {
      throw new AgentError(500, "Invalid artifact format");
    }
  }
}

let singleton: AgentService | undefined;

export function getAgentService(): AgentService {
  if (singleton === undefined) {
    singleton = new AgentService();
  }
  return singleton;
}
