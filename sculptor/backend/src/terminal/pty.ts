import path from "node:path";

import * as pty from "node-pty";

// PTY-backed terminals via node-pty, which retires the Python posix_spawn /
// fork-lock PTY-helper machinery (RW-SIMP-1) — node-pty handles the fork safely
// inside a multi-threaded process. Defaults + env scrubbing mirror
// spawned_pty_process.py so the frontend xterm client sees the same protocol.

export const DEFAULT_TERMINAL_COLS = 80;
export const DEFAULT_TERMINAL_ROWS = 24;
export const TERMINAL_TYPE = "xterm-256color";

const EXCLUDED_ENV_VAR_NAMES = new Set(["SESSION_TOKEN"]);
const EXCLUDED_ENV_VAR_PREFIXES = ["SCULPT_", "SCULPTOR_", "_PYI_"];

export function resolveShell(env: NodeJS.ProcessEnv = process.env): string {
  return env.SHELL ?? "/bin/bash";
}

// Builds the shell environment: the backend's env minus SESSION_TOKEN and the
// SCULPT_/SCULPTOR_/_PYI_ families (so Sculptor-on-Sculptor sessions don't point
// the inner sculpt CLI at the outer backend), with extra vars merged (PATH
// prepended) and TERM forced. Mirrors _scrub_shell_env.
export function buildShellEnv(
  extraEnv: Record<string, string> = {},
  envVarOverride = false,
  baseEnv: NodeJS.ProcessEnv = process.env,
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(baseEnv)) {
    if (value === undefined) {
      continue;
    }
    if (EXCLUDED_ENV_VAR_NAMES.has(key) || EXCLUDED_ENV_VAR_PREFIXES.some((prefix) => key.startsWith(prefix))) {
      continue;
    }
    env[key] = value;
  }
  for (const [key, value] of Object.entries(extraEnv)) {
    if (key === "PATH") {
      env.PATH = value + path.delimiter + (env.PATH ?? "");
    } else if (envVarOverride || !(key in env)) {
      env[key] = value;
    }
  }
  env.TERM = TERMINAL_TYPE;
  return env;
}

export interface SpawnPtyOptions {
  cwd: string;
  shell?: string;
  extraEnv?: Record<string, string>;
  envVarOverride?: boolean;
  cols?: number;
  rows?: number;
}

export interface PtyExitEvent {
  exitCode: number;
  signal?: number;
}

export interface PtyProcess {
  readonly pid: number;
  write(data: string): void;
  resize(cols: number, rows: number): void;
  kill(signal?: string): void;
  onData(callback: (data: string) => void): void;
  onExit(callback: (event: PtyExitEvent) => void): void;
}

export function spawnPty(options: SpawnPtyOptions): PtyProcess {
  const shell = options.shell ?? resolveShell();
  const child = pty.spawn(shell, [], {
    name: TERMINAL_TYPE,
    cols: options.cols ?? DEFAULT_TERMINAL_COLS,
    rows: options.rows ?? DEFAULT_TERMINAL_ROWS,
    cwd: options.cwd,
    env: buildShellEnv(options.extraEnv, options.envVarOverride),
  });
  return {
    pid: child.pid,
    write: (data) => child.write(data),
    resize: (cols, rows) => child.resize(cols, rows),
    kill: (signal) => child.kill(signal),
    onData: (callback) => {
      child.onData(callback);
    },
    onExit: (callback) => {
      child.onExit(callback);
    },
  };
}
