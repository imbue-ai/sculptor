// The Claude Code harness: the `Harness` implementation the supervisor (Task
// 5.1) drives, plus the Claude-specific identity surface (tool classification,
// model catalog, the session-file JSONL directory) the projection (Task 4.3)
// and resume (Task 5.4) read. Ports `claude_code_sdk/harness.py` (identity) and
// the per-turn lifecycle of `process_manager.py` (launch wiring) onto the
// long-lived `HarnessProcess` contract.

import { spawn, type ChildProcess } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join as joinPath } from "node:path";

import type { AgentRow, WorkspaceInitializationStrategy } from "~/db/schema";
import { newAgentMessageId } from "~/ids";
import {
  ASK_USER_QUESTION_TOOL_NAMES,
  DEFAULT_EFFORT,
  EXIT_PLAN_MODE_TOOL_NAMES,
  MODEL_SHORTNAME_MAP,
  PRE_COMPACT_CALLBACK_ID,
} from "~/harness/claude/constants";
import { readTaskListArtifact } from "~/harness/claude/artifacts";
import { serializeError } from "~/harness/claude/errors";
import {
  buildInitializeControlRequest,
  buildInterruptControlRequest,
  buildStdinUserMessage,
  getClaudeCommand,
  modelShortnameFor,
  resolveClaudeBinary,
} from "~/harness/claude/launch";
import { SculptorMcpServer, type UserQuestionAnswer } from "~/harness/claude/mcp";
import { ClaudeOutputProcessor } from "~/harness/claude/output_processor";
import {
  getTasksPath as resolveTasksPath,
  resolveJsonlDirectory,
} from "~/harness/claude/paths";
import {
  getCombinedSystemPrompt,
  getUserInstructions,
  type SetupReminder,
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
  // Re-resolve the injected `.env` for the agent at the start of each turn, so a
  // var added to `.sculptor/.env` after the agent launched is picked up on its
  // next message (the launch-time context.env is otherwise stale). Falls back to
  // context.env when omitted.
  resolveEnvForAgent?: (agent: AgentRow) => Record<string, string>;
  // The first-message setup-command reminder for the agent's workspace (a running
  // or failed workspace setup), or null. Prepended to the first user turn.
  setupReminderFor?: (agent: AgentRow) => SetupReminder | null;
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

// Marker file (in the agent state dir) recording that the conversation's first
// user message has been processed, so the env-var reminder fires only once and
// not again after an app restart.
const ENV_REMINDER_MARKER_FILE = "env_var_reminder_emitted";

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
  private interruptEscalationTimers: ReturnType<typeof setTimeout>[] = [];
  // The model from the most recent message that carried one, so a later turn
  // without an explicit model (an answer turn) reuses it.
  private lastModelName: string | null = null;
  private transcriptSequence = 0;
  // AUQ/plan answers delivered mid-turn via the MCP backchannel: their
  // RequestStarted is emitted on delivery, but the matching RequestSuccess is
  // deferred until the in-flight CLI invocation completes (the answer continues
  // the same turn). Mirrors process_manager's `_pending_answer_request_ids`.
  private readonly pendingAnswerRequestIds: string[] = [];

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
    // A mid-turn answer to an AUQ / ExitPlanMode dialog resolves the held MCP
    // `tools/call` that paused the running CLI — it must NOT start a new turn.
    // Only when there is no pending call (e.g. the answer arrives after the call
    // already resolved) does it fall through to a queued turn.
    if (message.object_type === "UserQuestionAnswerMessage") {
      const toolUseId = message.tool_use_id;
      if (
        typeof toolUseId === "string" &&
        this.mcpServer.hasPendingCall(toolUseId)
      ) {
        // Bracket the answer as its own request keyed by its message_id: emit
        // RequestStarted now and defer RequestSuccess until the turn completes,
        // so the derived status (which requires every chat-input id to have a
        // finished request) settles to READY. Ports `_try_deliver_answer_to_mcp`.
        const answerRequestId =
          typeof message.message_id === "string"
            ? message.message_id
            : newAgentMessageId();
        this.emit({
          object_type: "RequestStartedAgentMessage",
          message_id: newAgentMessageId(),
          source: "AGENT",
          request_id: answerRequestId,
        });
        this.pendingAnswerRequestIds.push(answerRequestId);
        this.mcpServer.deliverAnswer(message as unknown as UserQuestionAnswer);
        return;
      }
    }
    this.queue.push(message);
    void this.pump();
  }

  interrupt(): void {
    if (this.child === undefined || this.child.stdin === null) {
      return;
    }
    this.interrupted = true;
    // Graceful first: the real CLI honors a control_request and ends the turn.
    this.writeStdin(
      buildInterruptControlRequest(this.nextControlRequestId("interrupt")),
    );
    // Escalate for a CLI that ignores the control request (e.g. a sleeping
    // fake_claude, which exits on SIGTERM): stdin → SIGTERM → SIGKILL, mirroring
    // process_manager's interrupt escalation. Timers are cleared on close.
    this.clearInterruptEscalation();
    this.interruptEscalationTimers.push(
      setTimeout(() => this.killChildGroup("SIGTERM"), 1_000),
      setTimeout(() => this.killChildGroup("SIGKILL"), 5_000),
    );
  }

  private clearInterruptEscalation(): void {
    for (const timer of this.interruptEscalationTimers) {
      clearTimeout(timer);
    }
    this.interruptEscalationTimers = [];
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

    // A turn without an explicit model_name (an answer turn) inherits the last
    // selected model, then the agent's default — not just defaultModel, which is
    // null when the model was chosen on the first message rather than at create.
    if (typeof message.model_name === "string" && message.model_name !== "") {
      this.lastModelName = message.model_name;
    }
    const modelName =
      (typeof message.model_name === "string" && message.model_name !== ""
        ? message.model_name
        : null) ??
      this.lastModelName ??
      this.agent.defaultModel;
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

    // The env-var reminder is appended to the first chat message of the
    // conversation when the project has configured env vars. A marker file in
    // the agent state dir makes "first message" survive an app restart, so it is
    // not re-emitted on resume (process_manager is_first_user_message_of_conversation).
    const statePath = this.environment.getStatePath(this.agent.objectId);
    const reminderMarker = joinPath(statePath, ENV_REMINDER_MARKER_FILE);
    const isChatInput = message.object_type === "ChatInputUserMessage";
    const isFirstMessage = isChatInput && !existsSync(reminderMarker);
    // An answer turn (the agent's AUQ/plan dialog already resolved, so this is a
    // fresh CLI invocation) feeds the user's answers back as the prompt — the
    // message has no `text` (process_manager_utils.get_user_instructions).
    const userInstructions =
      message.object_type === "UserQuestionAnswerMessage"
        ? buildAnswerInstructions(message)
        : getUserInstructions({
            text: typeof message.text === "string" ? message.text : "",
            filePaths: Array.isArray(message.files)
              ? (message.files as string[])
              : undefined,
            enterPlanMode: message.enter_plan_mode === true,
            exitPlanMode: message.exit_plan_mode === true,
            envVarNames: Object.keys(this.context.env ?? {}),
            isFirstMessage,
            setupReminder: isFirstMessage
              ? (this.deps.setupReminderFor?.(this.agent) ?? null)
              : null,
          });
    // Persist the instructions the CLI received (diagnostics + the env-var-reminder
    // tests read state/tasks/<id>/user_instructions_<id>.txt) and mark the
    // conversation as started so the reminder fires only once.
    try {
      mkdirSync(statePath, { recursive: true });
      writeFileSync(
        joinPath(statePath, `user_instructions_${requestId}.txt`),
        userInstructions,
      );
      if (isChatInput) {
        writeFileSync(reminderMarker, "");
      }
    } catch {
      // Best-effort; never block a turn on these side files.
    }
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
      buildTaskListArtifactMessage: (sid) =>
        this.buildTaskListArtifactMessage(sid),
      isInterrupted: () => this.interrupted,
      now: () => this.now(),
    });
    this.mcpServer.setRespond((reqId, data) =>
      this.writeControlResponse(reqId, data),
    );

    await this.spawnAndDrive(argv, userInstructions, outputProcessor);

    // Settle any mid-turn answers delivered during this invocation: their
    // deferred RequestSuccess closes the request started at delivery time so the
    // derived status no longer treats them as in-flight.
    const interrupted = this.interrupted;
    while (this.pendingAnswerRequestIds.length > 0) {
      const answerRequestId = this.pendingAnswerRequestIds.shift() as string;
      this.emit({
        object_type: "RequestSuccessAgentMessage",
        message_id: newAgentMessageId(),
        source: "AGENT",
        request_id: answerRequestId,
        interrupted,
        approximate_creation_time: new Date(this.now()).toISOString(),
      });
    }

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
    // Re-resolve the .env each turn so a var added after launch is picked up.
    const injectedEnv =
      this.deps.resolveEnvForAgent?.(this.agent) ?? this.context.env;
    return new Promise<void>((resolve) => {
      const child = spawn(argv[0] as string, argv.slice(1), {
        cwd: this.environment.getWorkingDirectory(),
        env: { ...process.env, ...injectedEnv },
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
            this.recordTranscript("OUT", line);
            outputProcessor.processLine(line);
            if (outputProcessor.isTurnComplete()) {
              child.stdin?.end();
              // A CLI that emits a terminal frame but then keeps running (e.g.
              // fake_claude usage_limit emits the rate-limit frame, then blocks)
              // won't exit on stdin EOF — force it so the turn finalizes with the
              // error that was already recorded. Cleared on close.
              if (this.interruptEscalationTimers.length === 0) {
                this.interruptEscalationTimers.push(
                  setTimeout(() => this.killChildGroup("SIGTERM"), 1_000),
                  setTimeout(() => this.killChildGroup("SIGKILL"), 5_000),
                );
              }
            }
          }
        }
      });
      child.on("error", () => {
        // Spawn/exec failure surfaces as the turn ending; the missing-binary
        // case is handled earlier, so treat this as a clean turn end.
        resolve();
      });
      child.on("close", (code) => {
        this.clearInterruptEscalation();
        const remaining = this.stdoutBuffer.trim();
        if (remaining) {
          outputProcessor.processLine(remaining);
        }
        this.stdoutBuffer = "";
        outputProcessor.finalizeTurn();
        // A non-zero exit with no error frame, no interrupt, AND no completed
        // result is a crash: the process died unrecoverably mid-turn. A non-zero
        // exit AFTER the turn already produced its result frame (a slow/dirty
        // shutdown post-success) is NOT a crash. Treat a real crash as fatal —
        // exitCb drives the supervisor to run_state FAILED (→ ERROR + the
        // restore-agent prompt), not a recoverable REQUEST_ERROR.
        const isCrash =
          code !== 0 &&
          code !== null &&
          !this.interrupted &&
          outputProcessor.turnError === undefined &&
          !outputProcessor.isTurnComplete();
        this.child = undefined;
        if (isCrash) {
          this.finished = true;
          this.exitCb?.({
            error: {
              exception: "AgentCrashedError",
              args: [`Agent process exited with code ${code}`],
              traceback_dict: null,
            },
          });
        }
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
    this.recordTranscript("IN", line);
    try {
      this.child?.stdin?.write(line);
    } catch {
      // The stdin pipe may already be closed (e.g. after interrupt); ignore.
    }
  }

  // Read the per-task store ($HOME/.claude/tasks/<sessionId>), write a v2
  // TaskListArtifact JSON into the artifacts dir, and return the
  // UpdatedArtifactAgentMessage pointing at it (the projection's
  // getLastTaskListArtifact reads that file for the status pill's task widget).
  // Mirrors artifact_creation.get_file_artifact_messages(PLAN). Best-effort.
  private buildTaskListArtifactMessage(
    sessionId: string,
  ): Record<string, unknown> | null {
    try {
      // Resolve the per-task store like the CLI does, honoring $CLAUDE_CONFIG_DIR
      // from the env the CLI was launched with (tests isolate it per-case).
      const launchEnv = {
        ...process.env,
        ...(this.deps.resolveEnvForAgent?.(this.agent) ?? this.context.env),
      };
      const tasksDir = resolveTasksPath(
        this.environment.getUserHomeDirectory(),
        sessionId,
        launchEnv,
      );
      const { tasks } = readTaskListArtifact(tasksDir);
      const artifactsDir = this.environment.getArtifactsPath(
        this.agent.objectId,
      );
      mkdirSync(artifactsDir, { recursive: true });
      // A single, overwritten file: the serve endpoint (agent.artifact) returns
      // the first `PLAN-`-prefixed file it finds, so keeping exactly one ensures
      // a follow-up turn's status reflects the latest task list, not a stale one.
      const planPath = joinPath(artifactsDir, "PLAN-tasks.json");
      writeFileSync(
        planPath,
        JSON.stringify({
          object_type: "TaskListArtifact",
          version: 2,
          tasks,
        }),
      );
      return {
        object_type: "UpdatedArtifactAgentMessage",
        message_id: newAgentMessageId(),
        source: "AGENT",
        artifact: {
          object_type: "FileAgentArtifact",
          name: "PLAN",
          url: `file://${planPath}`,
        },
      };
    } catch {
      return null;
    }
  }

  // Append a diagnostic record of one piped line to the agent's transcript
  // (artifacts/tasks/<id>/transcript.jsonl), the file the diagnostics endpoint
  // surfaces. Best-effort — a transcript write must never break a turn. Ports
  // transcript_collector.TranscriptCollector (the fields Sculptor never parses).
  private recordTranscript(direction: "IN" | "OUT", line: string): void {
    try {
      const dir = this.environment.getArtifactsPath(this.agent.objectId);
      mkdirSync(dir, { recursive: true });
      let msgType = "non_json";
      try {
        const parsed = JSON.parse(line) as { type?: unknown };
        if (typeof parsed.type === "string") {
          msgType = parsed.type;
        } else {
          msgType = "non_object";
        }
      } catch {
        // Non-JSON line (verbose noise) — recorded as-is.
      }
      const entry = {
        sequence: this.transcriptSequence,
        direction,
        timestamp: this.now() / 1000,
        msg_type: msgType,
      };
      appendFileSync(joinPath(dir, "transcript.jsonl"), JSON.stringify(entry) + "\n");
      this.transcriptSequence += 1;
    } catch {
      // Best-effort only.
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

// Build the prompt for an answer turn (a fresh CLI invocation after the AUQ /
// plan dialog resolved): feed the user's answers back as text, since the
// UserQuestionAnswerMessage carries no `text`. Mirrors
// process_manager_utils.get_user_instructions' UserQuestionAnswerMessage branch
// (non-plan-approval case).
function buildAnswerInstructions(message: Record<string, unknown>): string {
  const answers = (message["answers"] as Record<string, string> | undefined) ?? {};
  const questionData = message["question_data"] as
    | { questions?: Array<{ question?: string; header?: string }> }
    | undefined;
  const questions = questionData?.questions ?? [];
  const lines = ["[Sculptor: The user answered your questions]", ""];
  for (const question of questions) {
    const value = answers[question.question ?? ""] ?? "";
    lines.push(`**${question.header ?? ""}:** ${value}`);
  }
  return lines.join("\n");
}
