import { spawn, type ChildProcess } from "node:child_process";

export interface RunOptions {
  cwd?: string;
  // Merged over the inherited process.env (so PATH etc. are preserved).
  env?: NodeJS.ProcessEnv;
  // Kill the child and reject if it hasn't exited within this many ms. Bounds a
  // wedged child (e.g. a git call blocked on a lock or an interactive prompt) so
  // the caller's promise can't hang forever. Defaults to DEFAULT_TIMEOUT_MS.
  timeoutMs?: number;
  // Kill the child and reject if combined stdout+stderr exceeds this many bytes.
  // Kept very generous (see DEFAULT_MAX_OUTPUT_BYTES) so large-but-legitimate
  // output — notably big `git diff`s — is never truncated; it only guards
  // against truly runaway output exhausting memory.
  maxOutputBytes?: number;
  // Only consulted by spawnBackgroundProcess: invoked if the child fails to
  // spawn (ENOENT/EACCES). Without an 'error' listener Node turns that event
  // into an uncaught exception that crashes the whole backend.
  onError?: (error: Error) => void;
}

export interface ProcessResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
}

export interface BackgroundProcess {
  pid: number | undefined;
  child: ChildProcess;
}

// Generous defaults: bound a wedged/runaway child without breaking slow-but-
// legitimate work (a large local clone) or large output (a big diff).
const DEFAULT_TIMEOUT_MS = 300_000;
const DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024 * 1024;

function resolveEnv(env: NodeJS.ProcessEnv | undefined): NodeJS.ProcessEnv {
  return env === undefined ? process.env : { ...process.env, ...env };
}

function splitCommand(command: readonly string[]): { cmd: string; args: string[] } {
  const [cmd, ...args] = command;
  if (cmd === undefined) {
    throw new Error("command must have at least one element");
  }
  return { cmd, args };
}

function describeCommand(command: readonly string[], cwd: string | undefined): string {
  return cwd === undefined ? command.join(" ") : `${command.join(" ")} (cwd ${cwd})`;
}

// Spawns a process, captures stdout/stderr, and resolves with the exit code on
// close. Rejects if the process fails to spawn, exceeds its timeout, or emits
// more than maxOutputBytes (a non-zero exit resolves with that code).
export function runProcessToCompletion(command: readonly string[], options: RunOptions = {}): Promise<ProcessResult> {
  return new Promise<ProcessResult>((resolve, reject) => {
    const { cmd, args } = splitCommand(command);
    const child = spawn(cmd, args, { cwd: options.cwd, env: resolveEnv(options.env), stdio: ["ignore", "pipe", "pipe"] });
    const context = describeCommand(command, options.cwd);
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const maxOutputBytes = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES;
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;

    const fail = (error: Error): void => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      try {
        child.kill("SIGKILL");
      } catch {
        // Already gone.
      }
      reject(error);
    };

    const timer = setTimeout(() => {
      fail(new Error(`process timed out after ${timeoutMs}ms: ${context}`));
    }, timeoutMs);

    const accumulate = (chunk: Buffer, append: (s: string) => void): void => {
      outputBytes += chunk.length;
      if (outputBytes > maxOutputBytes) {
        fail(new Error(`process output exceeded ${maxOutputBytes} bytes: ${context}`));
        return;
      }
      append(chunk.toString("utf8"));
    };

    child.stdout.on("data", (chunk: Buffer) => accumulate(chunk, (s) => (stdout += s)));
    child.stderr.on("data", (chunk: Buffer) => accumulate(chunk, (s) => (stderr += s)));
    child.on("error", (error) => fail(new Error(`process failed to run (${error.message}): ${context}`)));
    child.on("close", (code) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve({ exitCode: code, stdout, stderr });
    });
  });
}

// Spawns a long-lived process and returns its handle (pid + the ChildProcess,
// whose stdout/stderr/stdin streams the caller wires up). The caller — or the
// owning LocalEnvironment — is responsible for killing it.
export function spawnBackgroundProcess(command: readonly string[], options: RunOptions = {}): BackgroundProcess {
  const { cmd, args } = splitCommand(command);
  const child = spawn(cmd, args, { cwd: options.cwd, env: resolveEnv(options.env), stdio: ["pipe", "pipe", "pipe"] });
  // A spawn failure (ENOENT for a missing `cursor`/`xdg-open`, EACCES, …) emits
  // 'error'; without a listener Node escalates it to an uncaught exception that
  // crashes the backend. Always attach one. Callers that pass onError get the
  // failure with command+cwd context; otherwise it is swallowed (logged) so a
  // failed fire-and-forget launch can't take the process down.
  const context = describeCommand(command, options.cwd);
  child.on("error", (error) => {
    const wrapped = new Error(`process failed to run (${error.message}): ${context}`);
    if (options.onError !== undefined) {
      options.onError(wrapped);
    } else {
      console.error(wrapped.message);
    }
  });
  // Drain stdout/stderr so a background child writing more than the pipe buffer
  // (~64KB) on a stream nothing else consumes never blocks. Draining callers
  // attach their own 'data' listeners synchronously after this returns (before
  // any data event), so they still receive every chunk.
  child.stdout?.resume();
  child.stderr?.resume();
  return { pid: child.pid, child };
}
