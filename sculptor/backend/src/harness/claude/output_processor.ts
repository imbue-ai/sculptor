// Parses the Claude CLI's stream-json stdout into the persistent-message dicts
// the supervisor (Task 5.1) persists and the fold (Task 4.2) consumes. Ported
// from `claude_code_sdk/output_processor.py` (`ClaudeOutputProcessor`): the
// streaming partial assembler, the control protocol (auto-approve permissions,
// PreCompact hook callback, SDK-MCP routing), compaction detection, background
// tasks, turn metrics, warnings, and AUQ/ExitPlanMode/EnterPlanMode
// interception.
//
// Differences from the Python loop, which are timing-only (not message-shape):
//  - It is event-driven (one `processLine` call per stdout line) rather than a
//    blocking queue loop; `isTurnComplete()` replaces the loop predicate.
//  - The end-of-turn `get_context_usage` round-trip (which enriches TurnMetrics
//    with a context-token snapshot) is omitted; turn metrics still carry
//    duration/tokens, with `context_total_tokens` null.
//  - The Monitor deferred-completion grace + post-interrupt idle timeout (edge
//    cases for one tool / a hung CLI) are not ported.

import { newAgentMessageId } from "~/ids";
import { shouldRefreshTaskList } from "~/harness/claude/artifacts";
import {
  MCP_ASK_TOOL_FQN,
  MCP_EXIT_PLAN_MODE_TOOL_FQN,
  PLAN_FILE_SEGMENT,
  PLAN_FILE_WRITE_TOOL_NAMES,
  PRE_COMPACT_CALLBACK_ID,
  TRANSIENT_ERROR_CODES,
} from "~/harness/claude/constants";
import type { SerializedException } from "~/harness/claude/errors";
import type { SculptorMcpServer } from "~/harness/claude/mcp";
import { validateArguments } from "~/harness/claude/mcp";
import type {
  Block,
  ParsedResponse,
  ParsedStreamEvent,
  ToolUseMap,
} from "~/harness/claude/stream_parser";
import {
  extractMediaTagsFromText,
  makeTextBlock,
  makeToolUseBlock,
  parseClaudeLine,
  splitTextAndMedia,
} from "~/harness/claude/stream_parser";

export interface OutputProcessorDeps {
  // Emit a persistent-message dict (carrying object_type / message_id / source).
  emit: (message: Record<string, unknown>) => void;
  // Write a line (already newline-terminated) to the CLI's stdin.
  writeStdin: (line: string) => void;
  mcpServer: SculptorMcpServer;
  // Invoked once when the CLI reports its session id (system/init).
  onSessionId?: (sessionId: string) => void;
  // Invoked when a file-changing tool ran, so the workspace diff can refresh.
  onDiffNeeded?: () => void;
  // Read the per-task store for this session, write a PLAN TaskListArtifact file,
  // and return the UpdatedArtifactAgentMessage to emit (or null on failure).
  buildTaskListArtifactMessage?: (
    sessionId: string,
  ) => Record<string, unknown> | null;
  // Whether the current turn has been interrupted (suppresses error surfacing).
  isInterrupted?: () => boolean;
  now?: () => number;
}

// The terminal outcome of a turn, read by the harness after the CLI exits.
export interface TurnError {
  error: SerializedException;
  transient: boolean;
}

interface StreamingToolAccumulator {
  id: string;
  name: string;
  inputJson: string;
}

const RE_TRAILING_MEDIA_TAG = /<(?:img|video)\b[^>]*$/i;
const TUI_COMMANDS: ReadonlySet<string> = new Set([
  "config",
  "cost",
  "doctor",
  "fast",
  "help",
  "init",
  "listen",
  "login",
  "logout",
  "memory",
  "model",
  "permissions",
  "resume",
  "review",
  "status",
  "terminal-setup",
  "vim",
]);

export class ClaudeOutputProcessor {
  private readonly deps: OutputProcessorDeps;
  private readonly toolUseMap: ToolUseMap = new Map();

  // Turn lifecycle.
  foundFinalMessage = false;
  readonly pendingBackgroundTasks = new Set<string>();
  private pendingWakeup = false;
  // The CLI's session id (system/init), used to locate the per-task store.
  private sessionId: string | null = null;
  private readonly completedViaTaskUpdated = new Set<string>();
  private readonly turnStartTime: number;
  turnError: TurnError | undefined;
  private lastAssistantSeen = false;

  // Streaming state.
  private isStreamingTurn = false;
  private currentTurnId: string | null = null;
  private readonly completedStreamingBlocks = new Map<number, Block>();
  private readonly textAccumulators = new Map<number, string>();
  private readonly toolAccumulators = new Map<
    number,
    StreamingToolAccumulator
  >();
  private readonly extractedFileBlocks = new Map<number, Block[]>();
  private firstResponseMessageId: string | null = null;
  private usedFirstResponseId = false;
  private currentParentToolUseId: string | null = null;
  private lastResponseParentToolUseId: string | null = null;
  private readonly streamedTurnIds = new Set<string>();
  private bufferedPersistenceMessage: Record<string, unknown> | undefined;
  private readonly interceptedToolIds = new Set<string>();

  // Compaction.
  private autoCompactingEmitted = false;

  // Plan-file tracking (for ExitPlanMode approval question).
  private recentPlanFilePath: string | null = null;

  constructor(deps: OutputProcessorDeps) {
    this.deps = deps;
    this.turnStartTime = this.now();
  }

  private now(): number {
    return (this.deps.now ?? Date.now)();
  }

  private newId(): string {
    return newAgentMessageId();
  }

  private timestamp(): string {
    return new Date(this.now()).toISOString();
  }

  // The turn is done once the CLI emitted its result and no background tasks /
  // scheduled wakeup are still outstanding (mirrors the Python loop predicate).
  isTurnComplete(): boolean {
    return (
      this.foundFinalMessage &&
      this.pendingBackgroundTasks.size === 0 &&
      !this.pendingWakeup
    );
  }

  // --- Emit helpers ---------------------------------------------------------

  private emit(objectType: string, fields: Record<string, unknown> = {}): void {
    this.deps.emit({
      object_type: objectType,
      message_id: this.newId(),
      source: "AGENT",
      ...fields,
    });
  }

  private emitWarning(
    message: string,
    error: SerializedException | null,
  ): void {
    this.emit("WarningAgentMessage", {
      message,
      error,
      approximate_creation_time: this.timestamp(),
    });
  }

  // --- Main entry -----------------------------------------------------------

  processLine(line: string): void {
    if (!line.trim()) {
      return;
    }

    // Usage-limit rejection: the CLI pauses without a terminating result, so end
    // the turn with a transient error (SCU-1129).
    if (this.maybeRaiseUsageLimit(line)) {
      return;
    }

    // Control requests from the CLI (permissions, hook callbacks, MCP routing).
    if (this.maybeHandleControlRequest(line)) {
      return;
    }

    // Compaction start (system/status status=compacting) + completion handling.
    if (!this.autoCompactingEmitted) {
      this.maybeDetectCompactionStart(line);
    }
    if (this.autoCompactingEmitted && this.maybeHandleCompaction(line)) {
      return;
    }

    let parsed;
    try {
      parsed = parseClaudeLine(line, this.toolUseMap);
    } catch {
      const truncated = line.slice(0, 200) + (line.length > 200 ? "..." : "");
      this.emitWarning(
        `Received malformed output from Claude CLI (non-JSON line): ${truncated}`,
        null,
      );
      return;
    }
    if (parsed === null) {
      return;
    }
    if ("event" in parsed) {
      this.handleStreamEvent(parsed.event);
      return;
    }
    this.handleResponse(parsed.response);
  }

  // Called by the harness when the CLI process exits, to emit fallback metrics
  // for an interrupted/killed turn (no result message arrived).
  finalizeTurn(): void {
    if (!this.foundFinalMessage) {
      const elapsed = (this.now() - this.turnStartTime) / 1000;
      this.emit("TurnMetricsAgentMessage", {
        turn_metrics: makeTurnMetrics(elapsed, null, null),
      });
    }
  }

  // --- Response dispatch ----------------------------------------------------

  private handleResponse(response: ParsedResponse): void {
    switch (response.kind) {
      case "init":
        this.handleInit(response.sessionId);
        break;
      case "end":
        this.handleEnd(response);
        break;
      case "assistant":
        this.handleAssistant(response);
        break;
      case "tool_result":
        this.handleToolResult(response);
        break;
      case "task_started":
        this.handleTaskStarted(response);
        break;
      case "task_notification":
        this.handleTaskNotification(response);
        break;
      case "task_updated":
        if (["completed", "failed", "stopped"].includes(response.status)) {
          this.completedViaTaskUpdated.add(response.taskId);
        }
        break;
    }
  }

  private handleInit(sessionId: string): void {
    this.sessionId = sessionId;
    this.deps.onSessionId?.(sessionId);
    if (this.pendingWakeup) {
      this.pendingWakeup = false;
      this.foundFinalMessage = false;
    }
    // A new request cycle: the next MessageStart gets its own ChatMessage id.
    this.firstResponseMessageId = null;
    this.usedFirstResponseId = false;
  }

  private handleEnd(response: Extract<ParsedResponse, { kind: "end" }>): void {
    const elapsed = (this.now() - this.turnStartTime) / 1000;
    if (response.inputTokens !== null && response.outputTokens !== null) {
      this.emit("TurnMetricsAgentMessage", {
        turn_metrics: makeTurnMetrics(
          elapsed,
          response.inputTokens,
          response.outputTokens,
        ),
      });
    }

    if (response.isError) {
      if (this.deps.isInterrupted?.()) {
        // Interrupts are handled by the harness; suppress the error.
      } else if (response.result.startsWith("API Error")) {
        const transient = [...TRANSIENT_ERROR_CODES].some((code) =>
          response.result.startsWith(`API Error: ${code}`),
        );
        this.turnError = {
          error: {
            exception: transient ? "AgentTransientError" : "ClaudeAPIError",
            args: [response.result],
            traceback_dict: null,
          },
          transient,
        };
      } else {
        this.turnError = {
          error: {
            exception: "AgentClientError",
            args: [response.result],
            traceback_dict: null,
          },
          transient: false,
        };
      }
    } else if (!this.lastAssistantSeen && response.result) {
      // A non-error result with no assistant content (e.g. an unknown slash
      // command) — surface the result text as a warning.
      this.emitWarning(rewriteUnknownSkillMessage(response.result), null);
    }

    this.foundFinalMessage = true;

    // Clear background tasks that already completed mid-turn via task_updated.
    for (const taskId of this.completedViaTaskUpdated) {
      this.pendingBackgroundTasks.delete(taskId);
    }
  }

  private handleTaskStarted(
    response: Extract<ParsedResponse, { kind: "task_started" }>,
  ): void {
    this.pendingBackgroundTasks.add(response.taskId);
    this.emit("BackgroundTaskStartedAgentMessage", {
      background_task_id: response.taskId,
      tool_use_id: response.toolUseId,
      description: response.description,
      task_type: response.taskType,
    });
  }

  private handleTaskNotification(
    response: Extract<ParsedResponse, { kind: "task_notification" }>,
  ): void {
    this.pendingBackgroundTasks.delete(response.taskId);
    // A new turn always follows a notification; keep the loop open for it.
    this.foundFinalMessage = false;
    this.emit("BackgroundTaskNotificationAgentMessage", {
      background_task_id: response.taskId,
      tool_use_id: response.toolUseId,
      status: response.status,
      summary: response.summary,
      duration_seconds:
        response.durationMs !== null ? response.durationMs / 1000 : null,
      approximate_creation_time: this.timestamp(),
    });
  }

  // --- Assistant + tool-result (non-streamed + streamed-persistence) --------

  private handleAssistant(
    response: Extract<ParsedResponse, { kind: "assistant" }>,
  ): void {
    this.lastAssistantSeen = true;
    if (this.streamedTurnIds.has(response.messageId)) {
      // Already shown via streaming partials; emit only the persistence message.
      let messageId: string;
      if (!this.usedFirstResponseId && this.firstResponseMessageId !== null) {
        messageId = this.firstResponseMessageId;
        this.usedFirstResponseId = true;
      } else {
        messageId = this.newId();
      }
      const persistence = {
        object_type: "ResponseBlockAgentMessage",
        message_id: messageId,
        source: "AGENT",
        assistant_message_id: response.messageId,
        content: response.contentBlocks,
        parent_tool_use_id: response.parentToolUseId,
        approximate_creation_time: this.timestamp(),
      };
      for (const block of response.contentBlocks) {
        if (block.object_type === "ToolUseBlock") {
          this.recordToolUse(block);
          this.maybeInterceptTool(block);
        }
      }
      if (this.isStreamingTurn) {
        this.bufferedPersistenceMessage = persistence;
      } else {
        this.deps.emit(persistence);
      }
      return;
    }
    this.parseAssistantResponse(response);
  }

  private parseAssistantResponse(
    response: Extract<ParsedResponse, { kind: "assistant" }>,
  ): void {
    for (const block of response.contentBlocks) {
      if (block.object_type === "ToolUseBlock") {
        this.recordToolUse(block);
        this.maybeInterceptTool(block);
      }
    }
    if (this.currentTurnId === null) {
      this.currentTurnId = response.messageId;
    }
    this.deps.emit({
      object_type: "ResponseBlockAgentMessage",
      message_id: this.newId(),
      source: "AGENT",
      assistant_message_id: response.messageId,
      content: response.contentBlocks,
      parent_tool_use_id: response.parentToolUseId,
      approximate_creation_time: this.timestamp(),
    });
    this.lastResponseParentToolUseId = response.parentToolUseId;
  }

  private handleToolResult(
    response: Extract<ParsedResponse, { kind: "tool_result" }>,
  ): void {
    this.deps.emit({
      object_type: "ResponseBlockAgentMessage",
      message_id: this.newId(),
      source: "AGENT",
      assistant_message_id: this.currentTurnId ?? response.toolUseIds[0] ?? "",
      content: response.contentBlocks,
      parent_tool_use_id: response.parentToolUseId,
      approximate_creation_time: this.timestamp(),
    });
    if (response.scheduledWakeupFor !== null) {
      this.pendingWakeup = true;
    }
    // Refresh the workspace diff if a file-changing tool produced this result.
    let diffRefreshed = false;
    let taskListRefreshed = false;
    for (const toolUseId of response.toolUseIds) {
      const info = this.toolUseMap.get(toolUseId);
      if (info === undefined) {
        continue;
      }
      if (!diffRefreshed && shouldRefreshDiff(info.name, info.input)) {
        this.deps.onDiffNeeded?.();
        diffRefreshed = true;
      }
      // A TaskCreate/TaskUpdate changed the per-task store; re-publish the PLAN
      // artifact so the status pill's task widget reflects it (output_processor.py
      // should_refresh_task_list → get_file_artifact_messages(PLAN)).
      if (
        !taskListRefreshed &&
        this.sessionId !== null &&
        shouldRefreshTaskList(info.name)
      ) {
        const message = this.deps.buildTaskListArtifactMessage?.(this.sessionId);
        if (message != null) {
          this.deps.emit(message);
        }
        taskListRefreshed = true;
      }
    }
  }

  private recordToolUse(block: Block): void {
    const id = block.id as string;
    const name = block.name as string;
    const input = (block.input ?? {}) as Record<string, unknown>;
    this.toolUseMap.set(id, { name, input });
    this.maybeRecordPlanFileWrite(name, input);
  }

  // --- Stream events --------------------------------------------------------

  private handleStreamEvent(event: ParsedStreamEvent): void {
    switch (event.kind) {
      case "message_start": {
        this.isStreamingTurn = true;
        this.currentTurnId = event.messageId;
        this.streamedTurnIds.add(event.messageId);
        const newParent = event.parentToolUseId;
        if (
          this.firstResponseMessageId === null ||
          this.lastResponseParentToolUseId !== newParent
        ) {
          this.firstResponseMessageId = this.newId();
          this.usedFirstResponseId = false;
        }
        this.currentParentToolUseId = newParent;
        this.lastResponseParentToolUseId = newParent;
        break;
      }
      case "text_block_start":
        this.textAccumulators.set(event.index, "");
        break;
      case "tool_block_start":
        this.toolAccumulators.set(event.index, {
          id: event.toolId,
          name: event.toolName,
          inputJson: "",
        });
        break;
      case "text_delta": {
        const current = this.textAccumulators.get(event.index);
        if (current !== undefined) {
          this.textAccumulators.set(event.index, current + event.text);
          this.emitPartialMessage();
        }
        break;
      }
      case "tool_input_delta": {
        const acc = this.toolAccumulators.get(event.index);
        if (acc !== undefined) {
          acc.inputJson += event.partialJson;
        }
        break;
      }
      case "content_block_stop":
        this.finalizeBlockFromAccumulator(event.index);
        break;
      case "message_stop":
        this.handleMessageStop();
        break;
    }
  }

  private handleMessageStop(): void {
    this.emit("StreamingMessageCompleteAgentMessage");
    const buffered = this.bufferedPersistenceMessage;
    if (buffered !== undefined) {
      const streamedContent = this.materializeContent(false);
      if (streamedContent.length > 0) {
        buffered.content = streamedContent;
      }
      this.deps.emit(buffered);
      this.bufferedPersistenceMessage = undefined;
    }
    this.resetStreamingState();
  }

  private finalizeBlockFromAccumulator(index: number): void {
    const text = this.textAccumulators.get(index);
    if (text !== undefined) {
      this.textAccumulators.delete(index);
      const segments = splitTextAndMedia(text);
      const hasFiles = segments.some((s) => s.object_type === "FileBlock");
      const firstText = segments.find((s) => s.object_type === "TextBlock");
      if (firstText !== undefined) {
        this.completedStreamingBlocks.set(index, firstText);
      }
      const remaining: Block[] = [];
      let foundFirstText = false;
      for (const segment of segments) {
        if (!foundFirstText && segment.object_type === "TextBlock") {
          foundFirstText = true;
          continue;
        }
        remaining.push(segment);
      }
      if (remaining.length > 0) {
        const existing = this.extractedFileBlocks.get(index) ?? [];
        existing.push(...remaining);
        this.extractedFileBlocks.set(index, existing);
      }
      if (hasFiles) {
        this.emitPartialMessage();
      }
      return;
    }
    const toolData = this.toolAccumulators.get(index);
    if (toolData !== undefined) {
      this.toolAccumulators.delete(index);
      let input: Record<string, unknown> = {};
      if (toolData.inputJson) {
        try {
          input = JSON.parse(toolData.inputJson) as Record<string, unknown>;
        } catch {
          input = {};
        }
      }
      const toolBlock = makeToolUseBlock(toolData.id, toolData.name, input);
      this.completedStreamingBlocks.set(index, toolBlock);
      this.maybeRecordPlanFileWrite(toolData.name, input);
      this.maybeInterceptTool(toolBlock);
      this.toolUseMap.set(toolData.id, { name: toolData.name, input });
      this.emitPartialMessage();
    }
  }

  private emitPartialMessage(): void {
    const content = this.materializeContent(true);
    if (this.currentTurnId === null || this.firstResponseMessageId === null) {
      return;
    }
    this.deps.emit({
      object_type: "PartialResponseBlockAgentMessage",
      message_id: this.newId(),
      source: "AGENT",
      content,
      assistant_message_id: this.currentTurnId,
      first_response_message_id: this.firstResponseMessageId,
      parent_tool_use_id: this.currentParentToolUseId,
      approximate_creation_time: this.timestamp(),
    });
  }

  // Render index-addressed streaming state into ordered content (port of
  // `_materialize_content`). Filters empty TextBlocks, hides in-progress media
  // tags, and splices extracted media right after its source text.
  private materializeContent(includeInProgress: boolean): Block[] {
    const blocks: Block[] = [];
    const indices = new Set<number>([
      ...this.completedStreamingBlocks.keys(),
      ...(includeInProgress ? this.textAccumulators.keys() : []),
      ...this.extractedFileBlocks.keys(),
    ]);
    for (const idx of [...indices].sort((a, b) => a - b)) {
      const completed = this.completedStreamingBlocks.get(idx);
      if (completed !== undefined) {
        if (
          !(
            completed.object_type === "TextBlock" &&
            !(completed.text as string).trim()
          )
        ) {
          blocks.push(completed);
        }
      } else if (includeInProgress && this.textAccumulators.has(idx)) {
        const text = this.textAccumulators.get(idx) ?? "";
        let { cleanedText } = extractMediaTagsFromText(text);
        const trailing = RE_TRAILING_MEDIA_TAG.exec(cleanedText);
        if (trailing !== null) {
          cleanedText = cleanedText.slice(0, trailing.index);
        }
        if (cleanedText.trim()) {
          blocks.push(makeTextBlock(cleanedText));
        }
      }
      const extracted = this.extractedFileBlocks.get(idx);
      if (extracted !== undefined && extracted.length > 0) {
        blocks.push(...extracted);
      }
    }
    return blocks;
  }

  private resetStreamingState(): void {
    this.isStreamingTurn = false;
    this.completedStreamingBlocks.clear();
    this.textAccumulators.clear();
    this.toolAccumulators.clear();
    this.extractedFileBlocks.clear();
    this.currentParentToolUseId = null;
  }

  // --- AUQ / ExitPlanMode / EnterPlanMode interception ----------------------

  private maybeRecordPlanFileWrite(
    toolName: string,
    input: Record<string, unknown>,
  ): void {
    if (!PLAN_FILE_WRITE_TOOL_NAMES.has(toolName)) {
      return;
    }
    const filePath = input.file_path;
    if (typeof filePath === "string" && filePath.includes(PLAN_FILE_SEGMENT)) {
      this.recentPlanFilePath = filePath;
    }
  }

  private maybeInterceptTool(block: Block): void {
    if (this.maybeHandleAskUserQuestion(block)) {
      return;
    }
    if (this.maybeHandleExitPlanMode(block)) {
      return;
    }
    this.maybeHandleEnterPlanMode(block);
  }

  private maybeHandleAskUserQuestion(block: Block): boolean {
    if (block.name !== MCP_ASK_TOOL_FQN) {
      return false;
    }
    const id = block.id as string;
    if (this.interceptedToolIds.has(id)) {
      return true;
    }
    this.interceptedToolIds.add(id);
    const input = (block.input ?? {}) as Record<string, unknown>;
    if (validateArguments(MCP_ASK_TOOL_FQN, input) !== null) {
      return false;
    }
    this.emit("AskUserQuestionAgentMessage", {
      question_data: { ...input, tool_use_id: id },
    });
    this.deps.mcpServer.registerToolUseId(id, MCP_ASK_TOOL_FQN);
    return true;
  }

  private maybeHandleExitPlanMode(block: Block): boolean {
    if (block.name !== MCP_EXIT_PLAN_MODE_TOOL_FQN) {
      return false;
    }
    const id = block.id as string;
    if (this.interceptedToolIds.has(id)) {
      return true;
    }
    this.interceptedToolIds.add(id);
    this.emit("AskUserQuestionAgentMessage", {
      question_data: makePlanApprovalQuestion(id, this.recentPlanFilePath),
    });
    this.recentPlanFilePath = null;
    this.deps.mcpServer.registerToolUseId(id, MCP_EXIT_PLAN_MODE_TOOL_FQN);
    return true;
  }

  private maybeHandleEnterPlanMode(block: Block): boolean {
    if (block.name !== "EnterPlanMode") {
      return false;
    }
    const id = block.id as string;
    if (this.interceptedToolIds.has(id)) {
      return true;
    }
    this.interceptedToolIds.add(id);
    this.emit("PlanModeAgentMessage", { is_in_plan_mode: true });
    return true;
  }

  // --- Control protocol -----------------------------------------------------

  private maybeHandleControlRequest(line: string): boolean {
    let data: Record<string, unknown>;
    try {
      const parsed = JSON.parse(line) as unknown;
      if (typeof parsed !== "object" || parsed === null) {
        return false;
      }
      data = parsed as Record<string, unknown>;
    } catch {
      return false;
    }
    if (data.type !== "control_request") {
      return false;
    }
    const request = (data.request ?? {}) as Record<string, unknown>;
    const requestId =
      typeof data.request_id === "string" ? data.request_id : "";
    const subtype = request.subtype;
    if (subtype === "can_use_tool") {
      this.respondToControlRequest(requestId, {
        behavior: "allow",
        updatedInput: request.input ?? {},
      });
    } else if (subtype === "hook_callback") {
      this.handleHookCallback(requestId, request);
    } else if (subtype === "mcp_message") {
      this.handleMcpMessage(requestId, request);
    }
    return true;
  }

  private handleHookCallback(
    requestId: string,
    request: Record<string, unknown>,
  ): void {
    if (request.callback_id === PRE_COMPACT_CALLBACK_ID) {
      this.autoCompactingEmitted = true;
      this.emit("AutoCompactingAgentMessage");
    }
    this.respondToControlRequest(requestId, {});
  }

  private handleMcpMessage(
    requestId: string,
    request: Record<string, unknown>,
  ): void {
    const message = (request.message ?? {}) as Record<string, unknown>;
    if (request.server_name === "sculptor") {
      this.deps.mcpServer.handleMessage(requestId, message);
      return;
    }
    this.deps.mcpServer.respondUnknownServer(requestId, message.id);
  }

  private respondToControlRequest(
    requestId: string,
    responseData: Record<string, unknown>,
  ): void {
    const response = {
      type: "control_response",
      response: {
        subtype: "success",
        request_id: requestId,
        response: responseData,
      },
    };
    this.deps.writeStdin(JSON.stringify(response) + "\n");
  }

  // --- Compaction -----------------------------------------------------------

  private maybeDetectCompactionStart(line: string): void {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return;
    }
    if (
      data.type === "system" &&
      data.subtype === "status" &&
      data.status === "compacting"
    ) {
      this.autoCompactingEmitted = true;
      this.emit("AutoCompactingAgentMessage");
    }
  }

  private maybeHandleCompaction(line: string): boolean {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return false;
    }
    const msgType = data.type;
    const subtype = data.subtype;
    if (msgType === "user" && isSyntheticUser(data)) {
      this.completeAutoCompaction(extractSummaryText(data));
      return true;
    }
    if (msgType === "system" && subtype === "compact_boundary") {
      this.resetStreamingForCompaction();
      return true;
    }
    if (msgType === "assistant" || msgType === "result") {
      this.completeAutoCompaction(null);
      return false; // fall through so the assistant/result is still processed
    }
    return false;
  }

  private completeAutoCompaction(summaryText: string | null): void {
    this.autoCompactingEmitted = false;
    this.emit("AutoCompactingDoneAgentMessage");
    this.emit("ContextSummaryMessage", {
      content: summaryText ?? "Context was automatically compacted.",
      approximate_creation_time: this.timestamp(),
    });
  }

  private resetStreamingForCompaction(): void {
    this.firstResponseMessageId = null;
    this.usedFirstResponseId = false;
    this.resetStreamingState();
  }

  // --- Usage limit ----------------------------------------------------------

  private maybeRaiseUsageLimit(line: string): boolean {
    if (!line.includes("rate_limit_event")) {
      return false;
    }
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return false;
    }
    if (data.type !== "rate_limit_event") {
      return false;
    }
    const info = data.rate_limit_info;
    if (
      typeof info !== "object" ||
      info === null ||
      (info as Record<string, unknown>).status !== "rejected"
    ) {
      return false;
    }
    const overage = (info as Record<string, unknown>).overageStatus;
    if (overage === "allowed" || overage === "allowed_warning") {
      return false;
    }
    if (this.deps.isInterrupted?.()) {
      return false;
    }
    const message = formatUsageLimitMessage(
      (info as Record<string, unknown>).resetsAt,
    );
    this.turnError = {
      error: {
        exception: "AgentTransientError",
        args: [message],
        traceback_dict: null,
      },
      transient: true,
    };
    this.foundFinalMessage = true;
    return true;
  }
}

// --- Module helpers ---------------------------------------------------------

function makeTurnMetrics(
  durationSeconds: number,
  inputTokens: number | null,
  outputTokens: number | null,
): Record<string, unknown> {
  return {
    duration_seconds: durationSeconds,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    reasoning_tokens: null,
    changed_files: [],
    context_total_tokens: null,
    auto_compact_threshold: null,
  };
}

const GIT_BRANCH_COMMANDS = [
  "git commit",
  "git reset",
  "git revert",
  "git checkout",
  "git switch",
  "git merge",
  "git rebase",
  "git cherry-pick",
];
const DIFF_TOOLS: ReadonlySet<string> = new Set([
  "Write",
  "Edit",
  "MultiEdit",
  "Bash",
]);

function shouldRefreshDiff(
  toolName: string,
  toolInput: Record<string, unknown>,
): boolean {
  if (DIFF_TOOLS.has(toolName)) {
    return true;
  }
  const command =
    typeof toolInput.command === "string" ? toolInput.command : "";
  return GIT_BRANCH_COMMANDS.some((cmd) => command.includes(cmd));
}

// Mirrors `state/chat_state.make_plan_approval_question` (the question_data the
// fold's `makePlanApprovalQuestion` also reproduces).
function makePlanApprovalQuestion(
  toolUseId: string,
  planFilePath: string | null,
): Record<string, unknown> {
  return {
    questions: [
      {
        question: "Planning complete. How would you like to proceed?",
        header: "Plan approval",
        options: [
          {
            label: "Approve plan",
            description: "Proceed with implementing the plan",
          },
        ],
        multi_select: false,
        other_label: "Revise",
      },
    ],
    tool_use_id: toolUseId,
    plan_file_path: planFilePath,
  };
}

function isSyntheticUser(data: Record<string, unknown>): boolean {
  if (data.isSynthetic) {
    return true;
  }
  const message = data.message;
  return (
    typeof message === "object" &&
    message !== null &&
    (message as Record<string, unknown>).isSynthetic === true
  );
}

function extractSummaryText(data: Record<string, unknown>): string | null {
  const message = data.message;
  if (typeof message !== "object" || message === null) {
    return null;
  }
  const content = (message as Record<string, unknown>).content;
  if (typeof content === "string") {
    return content || null;
  }
  if (Array.isArray(content)) {
    for (const block of content) {
      if (
        typeof block === "object" &&
        block !== null &&
        (block as Record<string, unknown>).type === "text"
      ) {
        const text = (block as Record<string, unknown>).text;
        if (typeof text === "string" && text) {
          return text;
        }
      }
    }
  }
  return null;
}

function formatUsageLimitMessage(resetsAt: unknown): string {
  const base = "Claude usage limit reached.";
  if (typeof resetsAt === "number" && resetsAt > 0) {
    const resetLocal = new Date(resetsAt * 1000);
    if (!Number.isNaN(resetLocal.getTime())) {
      const pad = (n: number): string => String(n).padStart(2, "0");
      const formatted = `${resetLocal.getFullYear()}-${pad(resetLocal.getMonth() + 1)}-${pad(resetLocal.getDate())} ${pad(resetLocal.getHours())}:${pad(resetLocal.getMinutes())}:${pad(resetLocal.getSeconds())}`;
      return `${base} Your limit will reset at ${formatted}.`;
    }
  }
  return base;
}

function rewriteUnknownSkillMessage(message: string): string {
  if (!message.startsWith("Unknown skill:")) {
    return message;
  }
  const skillName = message.slice("Unknown skill:".length).trim();
  if (TUI_COMMANDS.has(skillName)) {
    return `The /${skillName} command is not available in Sculptor.`;
  }
  return message;
}
