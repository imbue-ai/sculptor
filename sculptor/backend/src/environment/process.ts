import { spawn, type ChildProcess } from "node:child_process";

export interface RunOptions {
  cwd?: string;
  // Merged over the inherited process.env (so PATH etc. are preserved).
  env?: NodeJS.ProcessEnv;
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

// Spawns a process, captures stdout/stderr, and resolves with the exit code on
// close. Rejects only if the process fails to spawn (a non-zero exit resolves
// with that code).
export function runProcessToCompletion(command: readonly string[], options: RunOptions = {}): Promise<ProcessResult> {
  return new Promise<ProcessResult>((resolve, reject) => {
    const { cmd, args } = splitCommand(command);
    const child = spawn(cmd, args, { cwd: options.cwd, env: resolveEnv(options.env), stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", reject);
    child.on("close", (code) => {
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
  return { pid: child.pid, child };
}
