import { updateAgent } from "~/db/repositories";
import type { Orm } from "~/db/orm";
import type { AgentRow, RunState } from "~/db/schema";
import { eventBus } from "~/events";
import type { ChangedEntityRef } from "~/events/types";
import { newAgentMessageId } from "~/ids";
import type { ProjectionCache } from "~/projection/cache";
import type { Harness, HarnessExitResult, HarnessProcess } from "~/runner/harness";
import { MessageWriter } from "~/runner/message_writer";

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
  private readonly writer: MessageWriter;

  constructor(private readonly deps: AgentSupervisorDeps) {
    this.agent = deps.agent;
    this.writer = new MessageWriter({
      orm: deps.orm,
      agentId: this.agent.objectId,
      cache: deps.cache,
      onStream: (message) => this.publishAgentMessage(message),
    });
  }

  get agentId(): string {
    return this.agent.objectId;
  }

  start(): void {
    this.setRunState("RUNNING");
    // Record that the agent's environment is ready (run_agent/v1.py emits this
    // before the first turn). The derived status gates on it: a coding agent
    // with a user message but no EnvironmentAcquired stays BUILDING. Written
    // through the writer so it folds into the warm cache + streams.
    this.writer.write({
      object_type: "EnvironmentAcquiredRunnerMessage",
      message_id: newAgentMessageId(),
      source: "RUNNER",
      approximate_creation_time: new Date().toISOString(),
    });
    this.process = this.deps.harness.launch({
      agent: this.agent,
      workingDirectory: this.deps.workingDirectory,
      env: this.deps.env,
    });
    this.process.onMessage((message) => this.handleMessage(message));
    this.process.onExit((result) => this.handleExit(result));
    // Let a harness report its model catalog before the first turn (pi). No-op
    // for harnesses that need nothing pre-turn (claude).
    this.process.warmUp?.();
  }

  private handleMessage(message: Record<string, unknown>): void {
    // The writer streams to the warm cache + bus immediately and persists with
    // coalescing (Task 5.2).
    this.writer.write(message);
  }

  private handleExit(result: HarnessExitResult): void {
    if (this.finalized) {
      return;
    }
    // Make any buffered partial durable before finalizing.
    this.writer.flush();
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

  clearSession(): void {
    this.process?.clearSession?.();
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
