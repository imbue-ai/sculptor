import {
  getAgent,
  listNonTerminalAgents,
  setAgentRunState,
} from "~/db/repositories";
import type { Orm } from "~/db/orm";
import type { AgentRow } from "~/db/schema";
import { ProjectionCache } from "~/projection/cache";
import { ConcurrencyLimiter } from "~/runner/concurrency";
import type { HarnessResolver } from "~/runner/harness";
import { AgentSupervisor, TERMINAL_RUN_STATES } from "~/runner/supervisor";

// On cutover the backend could face a large fleet of non-terminal agents; cap
// how many subprocesses we spawn at once. The Python spawner batches QUEUED in
// groups of 100 with no hard running cap (concurrent_implementation.py), so this
// bounds the startup thundering herd without regressing steady-state behavior.
const DEFAULT_RESUPERVISE_CONCURRENCY = 8;

export interface AgentRunnerDeps {
  orm: Orm;
  harnessFor: HarnessResolver;
  // Resolves the workspace working directory for an agent (Task 3.1/5.3). When
  // omitted, supervisors launch with an empty cwd (tests / harness-resolved).
  workingDirectoryFor?: (agent: AgentRow) => string;
  // Resolves the `.env`-injected environment for an agent's subprocess (Task
  // 7.6, per-repo over global). Omitted in tests → no extra env.
  envFor?: (agent: AgentRow) => Record<string, string>;
  cache?: ProjectionCache;
  resuperviseConcurrency?: number;
}

// Replaces the Python TaskService: owns the live supervisors and the
// start/stop/interrupt control surface, plus the startup re-supervision that is
// the crash-recovery / big-bang-cutover resume mechanism (RW-DATA-6).
export class AgentRunner {
  private readonly supervisors = new Map<string, AgentSupervisor>();

  constructor(private readonly deps: AgentRunnerDeps) {}

  private supervise(agent: AgentRow): void {
    if (this.supervisors.has(agent.objectId)) {
      return;
    }
    const harness = this.deps.harnessFor(agent);
    if (harness === undefined) {
      // Terminal agents (Task 3.4) and unknown harnesses are not chat-supervised.
      return;
    }
    const supervisor = new AgentSupervisor({
      orm: this.deps.orm,
      agent,
      harness,
      workingDirectory: this.deps.workingDirectoryFor?.(agent) ?? "",
      env: this.deps.envFor?.(agent),
      cache: this.deps.cache,
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

  sendUserMessage(agentId: string, message: Record<string, unknown>): void {
    this.supervisors.get(agentId)?.sendUserMessage(message);
  }

  getSupervisor(agentId: string): AgentSupervisor | undefined {
    return this.supervisors.get(agentId);
  }

  // Crash-recovery / cutover resume: reset every stuck RUNNING agent to QUEUED
  // (it will be relaunched and continue its model session via the CLI's own
  // --resume, Task 5.4), then start a supervisor for each non-terminal agent,
  // bounded so cutover doesn't spawn the whole fleet at once.
  async resuperviseOnStartup(): Promise<void> {
    const agents = listNonTerminalAgents(this.deps.orm);
    const limiter = new ConcurrencyLimiter(
      this.deps.resuperviseConcurrency ?? DEFAULT_RESUPERVISE_CONCURRENCY,
    );
    await Promise.all(
      agents.map((agent) =>
        limiter.run(async () => {
          let current = agent;
          if (current.runState === "RUNNING") {
            setAgentRunState(this.deps.orm, current.objectId, "QUEUED");
            current = { ...current, runState: "QUEUED" };
          }
          this.supervise(current);
        }),
      ),
    );
  }
}
