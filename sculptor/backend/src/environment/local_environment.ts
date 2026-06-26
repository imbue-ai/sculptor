import { constants as fsConstants } from "node:fs";
import { access, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import type { WorkspaceInitializationStrategy } from "~/db/schema";
import {
  artifactsPath,
  attachmentsPath,
  statePath,
  workingDirectory,
} from "~/environment/paths";
import {
  type BackgroundProcess,
  type ProcessResult,
  type RunOptions,
  runProcessToCompletion,
  spawnBackgroundProcess,
} from "~/environment/process";

export interface LocalEnvironmentOptions {
  // The workspace root (the absolute path stored as the workspace's
  // environment_id).
  root: string;
  initializationStrategy: WorkspaceInitializationStrategy;
  // Required for IN_PLACE (the user's repository checkout).
  repoHostPath?: string;
}

// The single concrete local execution environment. The Python abstract
// Environment / AgentExecutionEnvironment / ComputingEnvironment interfaces,
// their capability flags, and the registry indirection are all dropped: there
// is exactly one implementation, this one.
export class LocalEnvironment {
  private readonly root: string;
  private readonly initializationStrategy: WorkspaceInitializationStrategy;
  private readonly repoHostPath: string | undefined;
  private readonly backgroundProcesses = new Set<BackgroundProcess>();

  constructor(options: LocalEnvironmentOptions) {
    this.root = options.root;
    this.initializationStrategy = options.initializationStrategy;
    this.repoHostPath = options.repoHostPath;
  }

  // --- Path getters ---

  getUserHomeDirectory(): string {
    return os.homedir();
  }

  getRootPath(): string {
    return this.root;
  }

  getWorkspacePath(): string {
    return this.root;
  }

  getWorkingDirectory(): string {
    return workingDirectory(this.root, this.initializationStrategy, this.repoHostPath);
  }

  getStatePath(agentId: string): string {
    return statePath(this.root, agentId);
  }

  getArtifactsPath(agentId: string): string {
    return artifactsPath(this.root, agentId);
  }

  getAttachmentsPath(): string {
    return attachmentsPath(this.root);
  }

  // Identity for the local environment — there is no container path
  // translation. Kept because callers expect the methods.
  toHostPath(p: string): string {
    return p;
  }

  toEnvironmentPath(p: string): string {
    return p;
  }

  // --- File ops (async, so large reads don't block the event loop) ---

  async exists(p: string): Promise<boolean> {
    try {
      await access(p, fsConstants.F_OK);
      return true;
    } catch {
      return false;
    }
  }

  async readTextFile(p: string): Promise<string> {
    return readFile(p, "utf8");
  }

  async readBinaryFile(p: string): Promise<Buffer> {
    return readFile(p);
  }

  async writeFile(p: string, content: string | Uint8Array): Promise<void> {
    await mkdir(path.dirname(p), { recursive: true });
    await writeFile(p, content);
  }

  async deleteFileOrDirectory(p: string): Promise<void> {
    await rm(p, { recursive: true, force: true });
  }

  // --- Process ops ---

  runProcessToCompletion(command: readonly string[], options: RunOptions = {}): Promise<ProcessResult> {
    return runProcessToCompletion(command, { cwd: this.getWorkingDirectory(), ...options });
  }

  // Setup commands run to completion in the working directory.
  runSetupSubprocess(command: readonly string[], options: RunOptions = {}): Promise<ProcessResult> {
    return this.runProcessToCompletion(command, options);
  }

  runProcessInBackground(command: readonly string[], options: RunOptions = {}): BackgroundProcess {
    const handle = spawnBackgroundProcess(command, {
      cwd: this.getWorkingDirectory(),
      ...options,
      // Drop the handle and surface a spawn failure (ENOENT/EACCES) rather than
      // letting it crash the backend as an uncaught 'error' event.
      onError: (error) => {
        this.backgroundProcesses.delete(handle);
        options.onError?.(error);
      },
    });
    this.backgroundProcesses.add(handle);
    handle.child.once("close", () => this.backgroundProcesses.delete(handle));
    return handle;
  }

  isAlive(handle: BackgroundProcess): boolean {
    return handle.child.exitCode === null && handle.child.signalCode === null && !handle.child.killed;
  }

  // --- Teardown ---

  // Terminals (node-pty) are owned by the process-wide TerminalManager singleton
  // (src/terminal/instance.ts) that the terminal routes/services use, not by the
  // environment: a reconnecting xterm must outlive any single request. Workspace
  // deletion reaps them there (WorkspaceService.deleteWorkspace). The environment
  // only owns its background processes.

  // close() and destroy() both terminate tracked background processes so nothing
  // outlives the environment.
  close(): void {
    for (const handle of this.backgroundProcesses) {
      handle.child.kill("SIGTERM");
    }
    this.backgroundProcesses.clear();
  }

  destroy(): void {
    this.close();
  }
}
