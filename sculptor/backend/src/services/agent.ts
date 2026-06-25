import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { z } from "zod";

import { getOrm } from "~/db/orm";
import {
  appendAgentMessage,
  createAgent,
  deleteAgentMessage,
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
import { artifactsPath, workingDirectory } from "~/environment/paths";
import { revParseHead } from "~/git";
import { newAgentId, newAgentMessageId } from "~/ids";
import { projectionCache } from "~/projection/cache";
import { computeAgentView } from "~/projection/derived";
import { camelizeDeep } from "~/projection/to_wire";
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

const AGENT_CONFIG_OBJECT_TYPE: Record<AgentTypeName, string> = {
  claude: "ClaudeCodeSDKAgentConfig",
  pi: "PiAgentConfig",
  terminal: "TerminalAgentConfig",
  registered: "RegisteredTerminalAgentConfig",
};

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
    if (agentType === "terminal" && (prompt === null || prompt === "")) {
      throw new AgentError(422, "Terminal agents require a prompt");
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

    const agentId = newAgentId();
    const agent = createAgent(orm, {
      objectId: agentId,
      projectId: workspace.projectId,
      workspaceId,
      agentConfig: { object_type: AGENT_CONFIG_OBJECT_TYPE[agentType] },
      startingGitHash,
      systemPrompt: repo?.defaultSystemPrompt ?? null,
      defaultModel: input.model ?? null,
      title: input.name ?? null,
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
    updateAgent(orm, agentId, { claudeSessionId: null, piSessionId: null });
    eventBus.publish({
      kind: "agent_status",
      agentId,
      workspaceId: agent.workspaceId ?? undefined,
      projectId: agent.projectId,
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

  deleteMessage(agentId: string, messageId: string): void {
    const orm = getOrm();
    const agent = this.requireAgent(agentId);
    deleteAgentMessage(orm, messageId);
    // Drop the warm fold so the view recomputes without the deleted message.
    projectionCache.evict(agentId);
    eventBus.publish({
      kind: "agent_status",
      agentId,
      workspaceId: agent.workspaceId ?? undefined,
      projectId: agent.projectId,
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
    return {
      sessionId: agent.claudeSessionId ?? agent.piSessionId ?? null,
      transcriptFilePath: null,
      sculptorTranscriptFilePath:
        root === null
          ? null
          : path.join(artifactsPath(root, agentId), "transcript.jsonl"),
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
