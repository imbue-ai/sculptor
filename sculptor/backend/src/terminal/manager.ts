import { execFileSync } from "node:child_process";

import { type PtyProcess, type SpawnPtyOptions, spawnPty } from "~/terminal/pty";

// The shell basenames a reaped terminal pid is expected to be running.
const SHELL_COMMAND_NAMES = new Set(["sh", "bash", "zsh", "fish", "dash", "ksh", "tcsh", "csh"]);

// Best-effort identity check: a pid persisted by a prior backend run may have
// been recycled by the OS into an unrelated process, so confirm it still looks
// like a shell before killing it. `ps -o comm= -p <pid>` is portable across
// macOS/Linux; a login shell shows as `-bash`, so strip the leading `-` and
// compare the basename.
function looksLikeShellProcess(pid: number): boolean {
  try {
    const out = execFileSync("ps", ["-o", "comm=", "-p", String(pid)], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    if (out === "") {
      return false;
    }
    const basename = out.split("/").pop() ?? out;
    return SHELL_COMMAND_NAMES.has(basename.replace(/^-/, ""));
  } catch {
    // No such process, or ps unavailable — don't kill.
    return false;
  }
}

// SIGKILLs a stale shell pid left behind by a crashed/restarted backend so it
// isn't orphaned before a terminal agent relaunches (the Python reap behavior,
// using terminal_shell_pid stored on the agent). Guarded by a best-effort
// identity check so a recycled pid isn't killed; this is not a perfect check
// (we don't have the original start time), but it scopes the blast radius to a
// pid that was recycled into another shell. A no-op if the pid is already gone.
export function reapStalePid(pid: number): void {
  if (!looksLikeShellProcess(pid)) {
    return;
  }
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // Already gone — nothing to reap.
  }
}

// Per-workspace terminal registry: plain workspace terminals keyed by integer
// index, plus per-agent terminals (terminal agents) keyed by agent id. Backs
// the terminal WebSocket channels.
export class TerminalManager {
  private readonly byIndex = new Map<number, PtyProcess>();
  private readonly byAgent = new Map<string, PtyProcess>();
  // The workspace each plain (by-index) terminal belongs to, so a workspace
  // deletion can close exactly its terminals (the index alone is not scoped).
  private readonly workspaceByIndex = new Map<number, string>();

  getOrCreateTerminal(
    index: number,
    options: SpawnPtyOptions,
    workspaceId?: string,
  ): PtyProcess {
    const existing = this.byIndex.get(index);
    if (existing !== undefined) {
      return existing;
    }
    const terminal = spawnPty(options);
    this.byIndex.set(index, terminal);
    if (workspaceId !== undefined) {
      this.workspaceByIndex.set(index, workspaceId);
    }
    terminal.onExit(() => {
      this.byIndex.delete(index);
      this.workspaceByIndex.delete(index);
    });
    return terminal;
  }

  // Close every plain terminal belonging to a workspace (deletion teardown).
  closeWorkspaceTerminals(workspaceId: string): void {
    for (const [index, ws] of this.workspaceByIndex) {
      if (ws === workspaceId) {
        this.closeTerminal(index);
      }
    }
  }

  getTerminal(index: number): PtyProcess | undefined {
    return this.byIndex.get(index);
  }

  closeTerminal(index: number): void {
    const terminal = this.byIndex.get(index);
    if (terminal !== undefined) {
      terminal.kill();
      this.byIndex.delete(index);
      this.workspaceByIndex.delete(index);
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
