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
import { TerminalManager } from "~/terminal/manager";

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
// their capability flags, and the registry indirection are all dropped
// (RW-SIMP-1): there is exactly one implementation, this one.
export class LocalEnvironment {
  private readonly root: string;
  private readonly initializationStrategy: WorkspaceInitializationStrategy;
  private readonly repoHostPath: string | undefined;
  private readonly backgroundProcesses = new Set<BackgroundProcess>();
  private terminalManager: TerminalManager | undefined;

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
    const handle = spawnBackgroundProcess(command, { cwd: this.getWorkingDirectory(), ...options });
    this.backgroundProcesses.add(handle);
    handle.child.once("close", () => this.backgroundProcesses.delete(handle));
    return handle;
  }

  isAlive(handle: BackgroundProcess): boolean {
    return handle.child.exitCode === null && handle.child.signalCode === null && !handle.child.killed;
  }

  // --- Terminals (node-pty) ---

  startTerminalManager(): TerminalManager {
    this.terminalManager ??= new TerminalManager();
    return this.terminalManager;
  }

  stopTerminalManager(): void {
    this.terminalManager?.closeAll();
    this.terminalManager = undefined;
  }

  // close() and destroy() both terminate tracked background processes and
  // terminals so nothing outlives the environment.
  close(): void {
    this.stopTerminalManager();
    for (const handle of this.backgroundProcesses) {
      handle.child.kill("SIGTERM");
    }
    this.backgroundProcesses.clear();
  }

  destroy(): void {
    this.close();
  }
}
