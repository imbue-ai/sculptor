// The Claude Code harness: the `Harness` implementation the supervisor (Task
// 5.1) drives, plus the Claude-specific identity surface (tool classification,
// model catalog, the session-file JSONL directory) the projection (Task 4.3)
// and resume (Task 5.4) read. Ports `claude_code_sdk/harness.py` (identity) and
// the per-turn lifecycle of `process_manager.py` (launch wiring) onto the
// long-lived `HarnessProcess` contract.

import { spawn, type ChildProcess } from "node:child_process";

import type { AgentRow, WorkspaceInitializationStrategy } from "~/db/schema";
import { newAgentMessageId } from "~/ids";
import {
  ASK_USER_QUESTION_TOOL_NAMES,
  DEFAULT_EFFORT,
  EXIT_PLAN_MODE_TOOL_NAMES,
  MODEL_SHORTNAME_MAP,
  PRE_COMPACT_CALLBACK_ID,
} from "~/harness/claude/constants";
import { serializeError } from "~/harness/claude/errors";
import {
  buildInitializeControlRequest,
  buildInterruptControlRequest,
  buildStdinUserMessage,
  getClaudeCommand,
  modelShortnameFor,
  resolveClaudeBinary,
} from "~/harness/claude/launch";
import { SculptorMcpServer } from "~/harness/claude/mcp";
import { ClaudeOutputProcessor } from "~/harness/claude/output_processor";
import {
  getTasksPath as resolveTasksPath,
  resolveJsonlDirectory,
} from "~/harness/claude/paths";
import {
  getCombinedSystemPrompt,
  getUserInstructions,
} from "~/harness/claude/prompts";
import { isSessionIdValid } from "~/harness/claude/session";
import {
  readSessionIdState,
  readValidatedSessionIdState,
  writeSessionIdState,
  writeValidatedSessionIdState,
} from "~/harness/claude/validated_session_state";
import type {
  Harness,
  HarnessExitResult,
  HarnessLaunchContext,
  HarnessProcess,
} from "~/runner/harness";

// Re-exported so callers (and tests) keep importing it from the harness module.
export { computeClaudeJsonlDirectory } from "~/harness/claude/paths";

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
  // Test-only: resolve the `fake_claude.py` launch command for a model wire
  // value, or null for a real model. Mirrors process_manager's `_is_fake_claude`
  // branch; the runner wires this from the test harness's env (Task 9.5).
  resolveFakeClaudeCommand?: (
    modelName: string | null,
  ) => { python: string; script: string } | null;
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
  // Called when the CLI reports its session id, so the agent row can persist it
  // (Task 5.4 step 5). The on-disk state file is the authoritative resume
  // pointer; this is the additional row-level mirror.
  onSessionIdReported?: (agent: AgentRow, sessionId: string) => void;
  now?: () => number;
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
    return resolveJsonlDirectory(home, workingDirectory);
  }

  // The per-task JSON store directory (`$CLAUDE_CONFIG_DIR/tasks/<session_id>`).
  getTasksPath(home: string, sessionId: string): string {
    return resolveTasksPath(home, sessionId);
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

    const modelName =
      typeof message.model_name === "string"
        ? message.model_name
        : this.agent.defaultModel;
    const fakeClaude =
      this.deps.resolveFakeClaudeCommand?.(modelName ?? null) ?? null;

    let binaryPath = "";
    if (fakeClaude === null) {
      try {
        binaryPath = resolveClaudeBinary(this.deps.resolveBinaryPath);
      } catch (error) {
        this.failTurnFatally(requestId, error);
        return;
      }
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
    const sessionId = await this.resolveSessionId();
    const argv = getClaudeCommand({
      binaryPath,
      systemPrompt,
      sessionId,
      // fake_claude.py takes the raw model wire value (Python passes it verbatim);
      // real models map to the CLI `--model` shortname.
      modelShortname:
        fakeClaude !== null ? modelName : modelShortnameFor(modelName),
      enableStreaming: true,
      fastMode: message.fast_mode === true,
      effort:
        typeof message.effort === "string" ? message.effort : DEFAULT_EFFORT,
      pluginDirs: this.deps.pluginDirs,
      fakeClaude,
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

  // --- Session id (Task 5.4: validation + corrupt-tail + resume) ------------

  // Resolve the session id to pass to `claude --resume` for this turn. The
  // on-disk `session_id` state file is the authoritative pointer (the CLI
  // rewrites the session JSONL each turn). A valid session resumes and refreshes
  // the `validated_session_id` fallback; an invalid/missing one rolls back to
  // the last validated id (errored-with-restore, never silent loss); unset
  // starts fresh. Mirrors `process_manager.py:_process_single_message`.
  private async resolveSessionId(): Promise<string | null> {
    const agentId = this.agent.objectId;
    const rawSessionId = await readSessionIdState(this.environment, agentId);
    if (rawSessionId === null) {
      return null;
    }
    const valid = isSessionIdValid({
      home: this.environment.getUserHomeDirectory(),
      workingDirectory: this.environment.getWorkingDirectory(),
      sessionId: rawSessionId,
      isSessionRunning: false,
    });
    if (valid) {
      await writeValidatedSessionIdState(
        this.environment,
        agentId,
        rawSessionId,
      ).catch(() => undefined);
      return rawSessionId;
    }
    this.emitWarning(
      "Rolling back to the last valid session id - this means your last user message may not be in the agent context",
    );
    return readValidatedSessionIdState(this.environment, agentId);
  }

  private onSessionId(sessionId: string): void {
    void writeSessionIdState(
      this.environment,
      this.agent.objectId,
      sessionId,
    ).catch(() => undefined);
    this.deps.onSessionIdReported?.(this.agent, sessionId);
  }

  // --- I/O helpers ----------------------------------------------------------

  private emit(message: Record<string, unknown>): void {
    this.messageCb?.(message);
  }

  private emitWarning(message: string): void {
    this.emit({
      object_type: "WarningAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      message,
      error: null,
      approximate_creation_time: new Date(this.now()).toISOString(),
    });
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
