// The Claude Code harness: the `Harness` implementation the supervisor (Task
// 5.1) drives, plus the Claude-specific identity surface (tool classification,
// model catalog, the session-file JSONL directory) the projection (Task 4.3)
// and resume (Task 5.4) read. Ports `claude_code_sdk/harness.py` (identity) and
// the per-turn lifecycle of `process_manager.py` (launch wiring) onto the
// long-lived `HarnessProcess` contract.

import { spawn, type ChildProcess } from "node:child_process";
import { realpathSync } from "node:fs";
import path from "node:path";

import type { AgentRow, WorkspaceInitializationStrategy } from "~/db/schema";
import { newAgentMessageId } from "~/ids";
import {
  ASK_USER_QUESTION_TOOL_NAMES,
  CLAUDE_CONFIG_DIR_ENV_VAR,
  CLAUDE_DEFAULT_DIR_NAME,
  CLAUDE_PROJECTS_SUBDIRECTORY,
  CLAUDE_TASKS_SUBDIRECTORY,
  DEFAULT_EFFORT,
  EXIT_PLAN_MODE_TOOL_NAMES,
  MODEL_SHORTNAME_MAP,
  PRE_COMPACT_CALLBACK_ID,
  SESSION_ID_STATE_FILE_NAME,
} from "~/harness/claude/constants";
import {
  ClaudeBinaryNotFoundError,
  serializeError,
} from "~/harness/claude/errors";
import {
  buildInitializeControlRequest,
  buildInterruptControlRequest,
  buildStdinUserMessage,
  getClaudeCommand,
  modelShortnameFor,
} from "~/harness/claude/launch";
import { SculptorMcpServer } from "~/harness/claude/mcp";
import { ClaudeOutputProcessor } from "~/harness/claude/output_processor";
import {
  getCombinedSystemPrompt,
  getUserInstructions,
} from "~/harness/claude/prompts";
import type {
  Harness,
  HarnessExitResult,
  HarnessLaunchContext,
  HarnessProcess,
} from "~/runner/harness";

// The subset of `LocalEnvironment` (Task 3.1) the Claude harness uses; declared
// structurally so the harness stays decoupled from the concrete environment.
export interface ClaudeHarnessEnvironment {
  getUserHomeDirectory(): string;
  getWorkingDirectory(): string;
  getStatePath(agentId: string): string;
  getArtifactsPath(agentId: string): string;
  writeFile(p: string, content: string): Promise<void>;
  readTextFile(p: string): Promise<string>;
}

export interface ClaudeHarnessDeps {
  // Resolve the host `claude` binary path (or undefined when not installed).
  resolveBinaryPath: () => string | undefined;
  // Resolve the execution environment for an agent (paths + file ops).
  environmentFor: (agent: AgentRow) => ClaudeHarnessEnvironment;
  // The workspace initialization strategy (drives the environment-mode prompt).
  initializationStrategyFor: (
    agent: AgentRow,
  ) => WorkspaceInitializationStrategy;
  enableEntityMentions?: boolean;
  pluginDirs?: readonly string[];
  // Called when a file-changing tool ran, so the workspace diff can refresh.
  onDiffNeeded?: (agent: AgentRow) => void;
  now?: () => number;
}

// Honor $CLAUDE_CONFIG_DIR (SCU-1295), falling back to <home>/.claude.
function claudeConfigDir(
  home: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const custom = env[CLAUDE_CONFIG_DIR_ENV_VAR];
  return custom ? custom : path.join(home, CLAUDE_DEFAULT_DIR_NAME);
}

// Compute the Claude session-JSONL directory for a working directory. Claude
// sanitizes paths by replacing every non-alphanumeric character (except '-')
// with '-'. Mirrors `compute_claude_jsonl_directory`.
export function computeClaudeJsonlDirectory(
  home: string,
  workingDirectory: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const sanitized = workingDirectory.replace(/[^a-zA-Z0-9-]/g, "-");
  return path.join(
    claudeConfigDir(home, env),
    CLAUDE_PROJECTS_SUBDIRECTORY,
    sanitized,
  );
}

function resolveSymlink(p: string): string {
  try {
    return realpathSync(p);
  } catch {
    return p;
  }
}

export class ClaudeHarness implements Harness {
  readonly name = "claude_code";

  constructor(private readonly deps: ClaudeHarnessDeps) {}

  // --- Identity surface (ports `ClaudeCodeHarness`) -------------------------

  isAskUserQuestionTool(toolName: string): boolean {
    return ASK_USER_QUESTION_TOOL_NAMES.has(toolName);
  }

  isExitPlanModeTool(toolName: string): boolean {
    return EXIT_PLAN_MODE_TOOL_NAMES.has(toolName);
  }

  // Claude's model catalog is the static LLMModel→shortname map's keys.
  getAvailableModels(): string[] {
    return Object.keys(MODEL_SHORTNAME_MAP);
  }

  getSelectedModelId(agent: AgentRow): string | null {
    return agent.defaultModel ?? null;
  }

  // The session-file directory for an agent's working directory (Task 5.4 resume
  // reads `<dir>/<session_id>.jsonl`). Resolves symlinks like the CLI does.
  getJsonlPathForWorkingDirectory(
    home: string,
    workingDirectory: string,
  ): string {
    return computeClaudeJsonlDirectory(home, resolveSymlink(workingDirectory));
  }

  // The per-task JSON store directory (`$CLAUDE_CONFIG_DIR/tasks/<session_id>`).
  getTasksPath(home: string, sessionId: string): string {
    return path.join(
      claudeConfigDir(home),
      CLAUDE_TASKS_SUBDIRECTORY,
      sessionId,
    );
  }

  launch(context: HarnessLaunchContext): HarnessProcess {
    return new ClaudeHarnessProcess(this.deps, context);
  }
}

// One long-lived process per supervised Claude agent. Each user message starts a
// fresh `claude` CLI turn (matching Python's per-turn invocation), bracketed by
// RequestStarted/RequestSuccess|Failure so the fold (Task 4.2) finalizes turns.
class ClaudeHarnessProcess implements HarnessProcess {
  private messageCb: ((message: Record<string, unknown>) => void) | undefined;
  private exitCb: ((result: HarnessExitResult) => void) | undefined;

  private readonly environment: ClaudeHarnessEnvironment;
  private readonly mcpServer = new SculptorMcpServer(() => undefined);
  private readonly queue: Record<string, unknown>[] = [];
  private pumping = false;
  private finished = false;

  private child: ChildProcess | undefined;
  private stdoutBuffer = "";
  private interrupted = false;
  private sessionId: string | null = null;
  private sessionIdLoaded = false;
  private controlRequestCounter = 0;

  constructor(
    private readonly deps: ClaudeHarnessDeps,
    private readonly context: HarnessLaunchContext,
  ) {
    this.environment = deps.environmentFor(context.agent);
  }

  private get agent(): AgentRow {
    return this.context.agent;
  }

  private now(): number {
    return (this.deps.now ?? Date.now)();
  }

  onMessage(callback: (message: Record<string, unknown>) => void): void {
    this.messageCb = callback;
  }

  onExit(callback: (result: HarnessExitResult) => void): void {
    this.exitCb = callback;
  }

  sendUserMessage(message: Record<string, unknown>): void {
    if (this.finished) {
      return;
    }
    this.queue.push(message);
    void this.pump();
  }

  interrupt(): void {
    if (this.child === undefined || this.child.stdin === null) {
      return;
    }
    this.interrupted = true;
    this.writeStdin(
      buildInterruptControlRequest(this.nextControlRequestId("interrupt")),
    );
  }

  stop(): void {
    this.finished = true;
    this.killChildGroup("SIGTERM");
    this.child = undefined;
  }

  // --- Turn loop ------------------------------------------------------------

  private async pump(): Promise<void> {
    if (this.pumping) {
      return;
    }
    this.pumping = true;
    try {
      while (!this.finished && this.queue.length > 0) {
        const message = this.queue.shift();
        if (message !== undefined) {
          await this.runTurn(message);
        }
      }
    } finally {
      this.pumping = false;
    }
  }

  private async runTurn(message: Record<string, unknown>): Promise<void> {
    const requestId =
      typeof message.message_id === "string"
        ? message.message_id
        : newAgentMessageId();
    this.interrupted = false;
    this.emit({
      object_type: "RequestStartedAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      request_id: requestId,
    });

    let binaryPath: string | undefined;
    try {
      binaryPath = this.deps.resolveBinaryPath();
      if (binaryPath === undefined) {
        throw new ClaudeBinaryNotFoundError();
      }
    } catch (error) {
      this.failTurnFatally(requestId, error);
      return;
    }

    const userInstructions = getUserInstructions({
      text: typeof message.text === "string" ? message.text : "",
      filePaths: Array.isArray(message.files)
        ? (message.files as string[])
        : undefined,
      enterPlanMode: message.enter_plan_mode === true,
      exitPlanMode: message.exit_plan_mode === true,
    });
    const systemPrompt = getCombinedSystemPrompt({
      initializationStrategy: this.deps.initializationStrategyFor(this.agent),
      userSystemPrompt: this.agent.systemPrompt,
      enableEntityMentions: this.deps.enableEntityMentions,
    });
    const sessionId = await this.loadSessionId();
    const argv = getClaudeCommand({
      binaryPath,
      systemPrompt,
      sessionId,
      modelShortname: modelShortnameFor(
        typeof message.model_name === "string"
          ? message.model_name
          : this.agent.defaultModel,
      ),
      enableStreaming: true,
      fastMode: message.fast_mode === true,
      effort:
        typeof message.effort === "string" ? message.effort : DEFAULT_EFFORT,
      pluginDirs: this.deps.pluginDirs,
    });

    const outputProcessor = new ClaudeOutputProcessor({
      emit: (m) => this.emit(m),
      writeStdin: (line) => this.writeStdin(line),
      mcpServer: this.mcpServer,
      onSessionId: (sid) => this.onSessionId(sid),
      onDiffNeeded: this.deps.onDiffNeeded
        ? () => this.deps.onDiffNeeded?.(this.agent)
        : undefined,
      isInterrupted: () => this.interrupted,
      now: () => this.now(),
    });
    this.mcpServer.setRespond((reqId, data) =>
      this.writeControlResponse(reqId, data),
    );

    await this.spawnAndDrive(argv, userInstructions, outputProcessor);

    const finalRequestId = requestId;
    if (this.interrupted) {
      this.emit({
        object_type: "RequestSuccessAgentMessage",
        message_id: newAgentMessageId(),
        source: "AGENT",
        request_id: finalRequestId,
        interrupted: true,
        approximate_creation_time: new Date(this.now()).toISOString(),
      });
    } else if (outputProcessor.turnError !== undefined) {
      this.emit({
        object_type: "RequestFailureAgentMessage",
        message_id: newAgentMessageId(),
        source: "AGENT",
        request_id: finalRequestId,
        error: outputProcessor.turnError.error,
        approximate_creation_time: new Date(this.now()).toISOString(),
      });
    } else {
      this.emit({
        object_type: "RequestSuccessAgentMessage",
        message_id: newAgentMessageId(),
        source: "AGENT",
        request_id: finalRequestId,
        interrupted: false,
        approximate_creation_time: new Date(this.now()).toISOString(),
      });
    }
  }

  // Spawn the CLI, write the initialize + user-message stdin, and pump stdout
  // lines through the output processor until the turn completes or the CLI exits.
  private spawnAndDrive(
    argv: string[],
    userInstructions: string,
    outputProcessor: ClaudeOutputProcessor,
  ): Promise<void> {
    return new Promise<void>((resolve) => {
      const child = spawn(argv[0] as string, argv.slice(1), {
        cwd: this.environment.getWorkingDirectory(),
        env: { ...process.env, ...this.context.env },
        stdio: ["pipe", "pipe", "pipe"],
        detached: true,
      });
      this.child = child;
      this.stdoutBuffer = "";

      child.stdout?.on("data", (chunk: Buffer) => {
        this.stdoutBuffer += chunk.toString("utf8");
        let newlineIndex: number;
        while ((newlineIndex = this.stdoutBuffer.indexOf("\n")) !== -1) {
          const line = this.stdoutBuffer.slice(0, newlineIndex);
          this.stdoutBuffer = this.stdoutBuffer.slice(newlineIndex + 1);
          if (line.trim()) {
            outputProcessor.processLine(line);
            if (outputProcessor.isTurnComplete()) {
              child.stdin?.end();
            }
          }
        }
      });
      child.on("error", () => {
        // Spawn/exec failure surfaces as the turn ending; the missing-binary
        // case is handled earlier, so treat this as a clean turn end.
        resolve();
      });
      child.on("close", () => {
        const remaining = this.stdoutBuffer.trim();
        if (remaining) {
          outputProcessor.processLine(remaining);
        }
        this.stdoutBuffer = "";
        outputProcessor.finalizeTurn();
        this.child = undefined;
        resolve();
      });

      // Register the PreCompact hook, then deliver the user turn.
      this.writeStdin(
        buildInitializeControlRequest(
          PRE_COMPACT_CALLBACK_ID,
          this.nextControlRequestId("init"),
        ),
      );
      this.writeStdin(buildStdinUserMessage(userInstructions));
    });
  }

  private failTurnFatally(requestId: string, error: unknown): void {
    const serialized = serializeError(error);
    this.emit({
      object_type: "RequestFailureAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      request_id: requestId,
      error: serialized,
      approximate_creation_time: new Date(this.now()).toISOString(),
    });
    this.finished = true;
    this.exitCb?.({ error: serialized });
  }

  // --- Session id -----------------------------------------------------------

  private async loadSessionId(): Promise<string | null> {
    if (this.sessionIdLoaded) {
      return this.sessionId;
    }
    this.sessionIdLoaded = true;
    const stateFile = path.join(
      this.environment.getStatePath(this.agent.objectId),
      SESSION_ID_STATE_FILE_NAME,
    );
    try {
      this.sessionId =
        (await this.environment.readTextFile(stateFile)).trim() || null;
    } catch {
      this.sessionId = null;
    }
    return this.sessionId;
  }

  private onSessionId(sessionId: string): void {
    this.sessionId = sessionId;
    this.sessionIdLoaded = true;
    const stateFile = path.join(
      this.environment.getStatePath(this.agent.objectId),
      SESSION_ID_STATE_FILE_NAME,
    );
    void this.environment
      .writeFile(stateFile, sessionId)
      .catch(() => undefined);
  }

  // --- I/O helpers ----------------------------------------------------------

  private emit(message: Record<string, unknown>): void {
    this.messageCb?.(message);
  }

  private writeStdin(line: string): void {
    try {
      this.child?.stdin?.write(line);
    } catch {
      // The stdin pipe may already be closed (e.g. after interrupt); ignore.
    }
  }

  private writeControlResponse(
    requestId: string,
    responseData: Record<string, unknown>,
  ): void {
    this.writeStdin(
      JSON.stringify({
        type: "control_response",
        response: {
          subtype: "success",
          request_id: requestId,
          response: responseData,
        },
      }) + "\n",
    );
  }

  private nextControlRequestId(kind: string): string {
    this.controlRequestCounter += 1;
    return `req_${kind}_${this.controlRequestCounter}`;
  }

  private killChildGroup(signal: NodeJS.Signals): void {
    const child = this.child;
    if (child === undefined || child.pid === undefined) {
      return;
    }
    try {
      // Negative pid signals the whole process group (detached spawn), so the
      // CLI's foreground subprocesses die with it (SCU-211).
      process.kill(-child.pid, signal);
    } catch {
      try {
        child.kill(signal);
      } catch {
        // Already dead.
      }
    }
  }
}
