import { appendAgentMessage, updateAgent } from "~/db/repositories";
import type { Orm } from "~/db/orm";
import type { AgentRow, RunState } from "~/db/schema";
import { eventBus } from "~/events";
import type { ChangedEntityRef } from "~/events/types";
import { ProjectionCache, projectionCache } from "~/projection/cache";
import type { Harness, HarnessExitResult, HarnessProcess } from "~/runner/harness";

export const TERMINAL_RUN_STATES: ReadonlySet<RunState> = new Set<RunState>([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "DELETED",
]);

export interface AgentSupervisorDeps {
  orm: Orm;
  agent: AgentRow;
  harness: Harness;
  workingDirectory: string;
  env?: Record<string, string>;
  cache?: ProjectionCache;
}

// One async supervisor per running agent — on the event loop, no thread, no
// ConcurrencyGroup (RW-SIMP-1). It launches the harness CLI subprocess,
// persists each emitted message (append-only log), updates the warm cache,
// publishes bus events, and maintains run_state. Mirrors the per-task lifecycle
// of the Python TaskService without the thread/queue machinery.
export class AgentSupervisor {
  private agent: AgentRow;
  private process: HarnessProcess | undefined;
  private finalized = false;

  constructor(private readonly deps: AgentSupervisorDeps) {
    this.agent = deps.agent;
  }

  private get cache(): ProjectionCache {
    return this.deps.cache ?? projectionCache;
  }

  get agentId(): string {
    return this.agent.objectId;
  }

  start(): void {
    this.setRunState("RUNNING");
    this.process = this.deps.harness.launch({
      agent: this.agent,
      workingDirectory: this.deps.workingDirectory,
      env: this.deps.env,
    });
    this.process.onMessage((message) => this.handleMessage(message));
    this.process.onExit((result) => this.handleExit(result));
  }

  private handleMessage(message: Record<string, unknown>): void {
    const { orm } = this.deps;
    try {
      appendAgentMessage(orm, this.agentId, message);
    } catch {
      // A malformed message that fails the append invariants is not persisted;
      // never let it crash the supervisor.
      return;
    }
    this.cache.applyMessage(orm, this.agentId, message);
    this.publishAgentMessage(message);
  }

  private handleExit(result: HarnessExitResult): void {
    if (this.finalized) {
      return;
    }
    this.finalize(result.error !== undefined ? "FAILED" : "SUCCEEDED", result.error ?? null);
  }

  // --- Control ops (called by the interaction endpoints, Task 6.8) ---

  sendUserMessage(message: Record<string, unknown>): void {
    this.process?.sendUserMessage(message);
  }

  interrupt(): void {
    // The harness emits a stopped/RequestStopped message in response; run_state
    // stays RUNNING until the turn actually ends.
    this.process?.interrupt();
  }

  stop(): void {
    if (this.finalized) {
      return;
    }
    this.process?.stop();
    this.finalize("CANCELLED", null);
  }

  isFinalized(): boolean {
    return this.finalized;
  }

  // --- State transitions + events ---

  private finalize(runState: RunState, error: unknown): void {
    this.finalized = true;
    updateAgent(this.deps.orm, this.agentId, { runState, error });
    this.agent = { ...this.agent, runState, error };
    this.publishAgentStatus();
    this.publishDataModelChange([{ type: "agent", id: this.agentId }]);
  }

  private setRunState(runState: RunState): void {
    updateAgent(this.deps.orm, this.agentId, { runState });
    this.agent = { ...this.agent, runState };
    this.publishAgentStatus();
  }

  // Publish a data-model change (notification / workspace / agent row mutations)
  // so the projection folds it into user_update / finished_request_ids (Task 4.4).
  // Agent-only refs are a no-op for user_update by design (agent changes flow via
  // agent_status), but a notification/workspace ref or a requestId is delivered.
  publishDataModelChange(changedEntities: ChangedEntityRef[], requestId?: string): void {
    eventBus.publish({ kind: "data_model_change", changedEntities, requestId });
  }

  private publishAgentStatus(): void {
    eventBus.publish({
      kind: "agent_status",
      agentId: this.agentId,
      workspaceId: this.agent.workspaceId ?? undefined,
      projectId: this.agent.projectId,
    });
  }

  private publishAgentMessage(message: Record<string, unknown>): void {
    eventBus.publish({
      kind: "agent_message",
      agentId: this.agentId,
      workspaceId: this.agent.workspaceId ?? undefined,
      projectId: this.agent.projectId,
      message,
    });
  }
}
