import { type PtyProcess, type SpawnPtyOptions, spawnPty } from "~/terminal/pty";

// SIGKILLs a stale shell pid left behind by a crashed/restarted backend so it
// isn't orphaned before a terminal agent relaunches (the Python reap behavior,
// using terminal_shell_pid stored on the agent — Task 2.3). A no-op if the pid
// is already gone (ESRCH).
export function reapStalePid(pid: number): void {
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // Already gone — nothing to reap.
  }
}

// Per-workspace terminal registry: plain workspace terminals keyed by integer
// index, plus per-agent terminals (terminal agents) keyed by agent id. Backs
// the terminal WebSocket channels (Task 6.9).
export class TerminalManager {
  private readonly byIndex = new Map<number, PtyProcess>();
  private readonly byAgent = new Map<string, PtyProcess>();

  getOrCreateTerminal(index: number, options: SpawnPtyOptions): PtyProcess {
    const existing = this.byIndex.get(index);
    if (existing !== undefined) {
      return existing;
    }
    const terminal = spawnPty(options);
    this.byIndex.set(index, terminal);
    terminal.onExit(() => {
      this.byIndex.delete(index);
    });
    return terminal;
  }

  getTerminal(index: number): PtyProcess | undefined {
    return this.byIndex.get(index);
  }

  closeTerminal(index: number): void {
    const terminal = this.byIndex.get(index);
    if (terminal !== undefined) {
      terminal.kill();
      this.byIndex.delete(index);
    }
  }

  getOrCreateAgentTerminal(agentId: string, options: SpawnPtyOptions): PtyProcess {
    const existing = this.byAgent.get(agentId);
    if (existing !== undefined) {
      return existing;
    }
    const terminal = spawnPty(options);
    this.byAgent.set(agentId, terminal);
    terminal.onExit(() => {
      this.byAgent.delete(agentId);
    });
    return terminal;
  }

  getAgentTerminal(agentId: string): PtyProcess | undefined {
    return this.byAgent.get(agentId);
  }

  closeAgentTerminal(agentId: string): void {
    const terminal = this.byAgent.get(agentId);
    if (terminal !== undefined) {
      terminal.kill();
      this.byAgent.delete(agentId);
    }
  }

  // Kills every terminal and frees its fds (teardown path the test harness
  // waits on).
  closeAll(): void {
    for (const terminal of this.byIndex.values()) {
      terminal.kill();
    }
    for (const terminal of this.byAgent.values()) {
      terminal.kill();
    }
    this.byIndex.clear();
    this.byAgent.clear();
  }
}
