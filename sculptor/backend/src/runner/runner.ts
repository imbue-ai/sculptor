import {
  getAgent,
  listNonTerminalAgents,
  setAgentRunState,
} from "~/db/repositories";
import type { Orm } from "~/db/orm";
import type { AgentRow } from "~/db/schema";
import { ProjectionCache } from "~/projection/cache";
import type { HarnessResolver } from "~/runner/harness";
import { AgentSupervisor, TERMINAL_RUN_STATES } from "~/runner/supervisor";

export interface AgentRunnerDeps {
  orm: Orm;
  harnessFor: HarnessResolver;
  // Resolves the workspace working directory for an agent. When omitted,
  // supervisors launch with an empty cwd (tests / harness-resolved).
  workingDirectoryFor?: (agent: AgentRow) => string;
  // Resolves the `.env`-injected environment for an agent's subprocess (per-repo
  // over global). Omitted in tests → no extra env.
  envFor?: (agent: AgentRow) => Record<string, string>;
  cache?: ProjectionCache;
}

// Replaces the Python TaskService: owns the live supervisors and the
// start/stop/interrupt control surface, plus the startup re-supervision that is
// the crash-recovery / cutover resume mechanism.
export class AgentRunner {
  private readonly supervisors = new Map<string, AgentSupervisor>();

  constructor(private readonly deps: AgentRunnerDeps) {}

  private supervise(agent: AgentRow): void {
    if (this.supervisors.has(agent.objectId)) {
      return;
    }
    const harness = this.deps.harnessFor(agent);
    if (harness === undefined) {
      // Terminal agents and unknown harnesses are not chat-supervised.
      return;
    }
    const supervisor = new AgentSupervisor({
      orm: this.deps.orm,
      agent,
      harness,
      workingDirectory: this.deps.workingDirectoryFor?.(agent) ?? "",
      env: this.deps.envFor?.(agent),
      cache: this.deps.cache,
      // Evict the supervisor from the live map on ANY terminal outcome (natural
      // SUCCEEDED/FAILED exit as well as stop/CANCELLED), so a long-lived server
      // doesn't accumulate one dead supervisor per agent ever run. The guard
      // below keys on identity so a stale callback from a previous supervisor
      // can't remove a freshly re-supervised one.
      onDispose: (supervisorRef) => {
        if (this.supervisors.get(agent.objectId) === supervisorRef) {
          this.supervisors.delete(agent.objectId);
        }
      },
    });
    this.supervisors.set(agent.objectId, supervisor);
    supervisor.start();
  }

  startAgent(agentId: string): void {
    const agent = getAgent(this.deps.orm, agentId);
    if (
      agent === undefined ||
      agent.isDeleted ||
      TERMINAL_RUN_STATES.has(agent.runState)
    ) {
      return;
    }
    this.supervise(agent);
  }

  stopAgent(agentId: string): void {
    const supervisor = this.supervisors.get(agentId);
    if (supervisor !== undefined) {
      supervisor.stop();
      this.supervisors.delete(agentId);
    }
  }

  interruptAgent(agentId: string): void {
    this.supervisors.get(agentId)?.interrupt();
  }

  clearSession(agentId: string): void {
    this.supervisors.get(agentId)?.clearSession();
  }

  sendUserMessage(agentId: string, message: Record<string, unknown>): void {
    this.supervisors.get(agentId)?.sendUserMessage(message);
  }

  getSupervisor(agentId: string): AgentSupervisor | undefined {
    return this.supervisors.get(agentId);
  }

  // Crash-recovery / cutover resume: reset every stuck RUNNING agent to QUEUED
  // (it will be relaunched and continue its model session via the CLI's own
  // --resume), then start a supervisor for each non-terminal agent.
  //
  // This runs synchronously per agent: `supervise` launches the subprocess via a
  // non-blocking spawn that returns immediately, so there is nothing to await and
  // no concurrent startup to bound. (An earlier ConcurrencyLimiter wrapped this
  // but released its slot the instant the spawn returned — it gated nothing — so
  // it was removed as inert indirection.) The method stays async for callers that
  // await startup completion.
  async resuperviseOnStartup(): Promise<void> {
    const agents = listNonTerminalAgents(this.deps.orm);
    for (const agent of agents) {
      let current = agent;
      if (current.runState === "RUNNING") {
        setAgentRunState(this.deps.orm, current.objectId, "QUEUED");
        current = { ...current, runState: "QUEUED" };
      }
      this.supervise(current);
      // Re-deliver any turn that was in-flight or queued at shutdown so the agent
      // resumes and leaves RUNNING. Only on this resupervise path — a fresh start
      // delivers its first message explicitly.
      this.supervisors.get(current.objectId)?.replayUnprocessedMessages();
    }
  }
}
