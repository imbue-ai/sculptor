import path from "node:path";

import * as pty from "node-pty";

// PTY-backed terminals via node-pty, which retires the Python posix_spawn /
// fork-lock PTY-helper machinery — node-pty handles the fork safely inside a
// multi-threaded process. Defaults + env scrubbing mirror spawned_pty_process.py
// so the frontend xterm client sees the same protocol.

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
    if (
      EXCLUDED_ENV_VAR_NAMES.has(key) ||
      EXCLUDED_ENV_VAR_PREFIXES.some((prefix) => key.startsWith(prefix))
    ) {
      continue;
    }
    env[key] = value;
  }
  for (const [key, value] of Object.entries(extraEnv)) {
    if (key === "PATH") {
      // Only join with the base PATH when it's non-empty: appending a delimiter
      // to an empty base yields a trailing-empty element, which many shells read
      // as the current directory — an unintended (and unsafe) PATH entry.
      const basePath = env.PATH ?? "";
      env.PATH = basePath === "" ? value : value + path.delimiter + basePath;
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

// The terminal output buffer is replayed to every (re)connecting client so the
// xterm renders the session so far (e.g. the shell's prompt) even on a second
// connection. Bounded so a chatty long-lived shell can't grow it without limit;
// the tail is kept (matches what a reconnecting client cares about).
const MAX_OUTPUT_BUFFER_BYTES = 1_000_000;

// Shown when the shell exits, so the user isn't left staring at a frozen
// terminal. Mirrors local_terminal_manager.py's `\r\n[Process exited]\r\n`.
const PROCESS_EXITED_NOTICE = "\r\n[Process exited]\r\n";

export interface PtyProcess {
  readonly pid: number;
  write(data: string): void;
  resize(cols: number, rows: number): void;
  kill(signal?: string): void;
  onData(callback: (data: string) => void): void;
  onExit(callback: (event: PtyExitEvent) => void): void;
  // Atomically return the buffered output so far AND register `callback` for
  // future output (no gap in which output is lost between the two). The returned
  // `unsubscribe` removes the callback when the consumer (e.g. a closed socket)
  // goes away.
  subscribe(callback: (data: string) => void): {
    buffered: string;
    unsubscribe: () => void;
  };
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
  let buffer = "";
  const listeners = new Set<(data: string) => void>();
  const emit = (data: string): void => {
    buffer += data;
    if (buffer.length > MAX_OUTPUT_BUFFER_BYTES) {
      buffer = buffer.slice(buffer.length - MAX_OUTPUT_BUFFER_BYTES);
    }
    for (const listener of listeners) {
      listener(data);
    }
  };
  child.onData((data) => emit(data));
  // Surface the exit in the output stream (so connected clients render it and a
  // later reconnect replays it) BEFORE any onExit consumer closes its socket.
  child.onExit(() => emit(PROCESS_EXITED_NOTICE));
  return {
    pid: child.pid,
    write: (data) => child.write(data),
    resize: (cols, rows) => child.resize(cols, rows),
    kill: (signal) => child.kill(signal),
    onData: (callback) => {
      listeners.add(callback);
    },
    onExit: (callback) => {
      child.onExit(callback);
    },
    subscribe: (callback) => {
      listeners.add(callback);
      return {
        buffered: buffer,
        unsubscribe: () => listeners.delete(callback),
      };
    },
  };
}
