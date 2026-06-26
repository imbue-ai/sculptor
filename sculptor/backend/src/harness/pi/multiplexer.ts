// The per-turn event multiplexer — ported from `pi_agent/agent_wrapper.py`'s
// `_dispatch_event` + `_handle_*` + `_TurnState`. It folds pi's three RPC lanes
// (response / extension_ui_request / session events) into the persistent-message
// dicts the supervisor persists and the fold consumes:
// streaming text → PartialResponseBlock, finalized messages + tool results →
// ResponseBlock, dialogs → AskUserQuestion, compaction → AutoCompacting,
// subagent/background lifecycle → BackgroundTask*.

import { newAgentMessageId } from "~/ids";
import {
  type Block,
  getToolInvocationString,
  makeTextBlock,
  makeToolResultBlock,
  makeToolUseBlock,
} from "~/harness/claude/stream_parser";
import type { AskUserQuestionData } from "~/harness/claude/mcp";
import {
  type BackgroundTaskCompletion,
  formatBackgroundCompletion,
  parseBackgroundCompletion,
  parseBackgroundStart,
} from "~/harness/pi/background";
import {
  ASK_USER_QUESTION_TOOL_NAME,
  buildAskUserQuestionData,
  EXIT_PLAN_MODE_TOOL_NAME,
  makePlanApprovalQuestion,
  PLAN_APPROVAL_DIALOG_TITLE,
} from "~/harness/pi/backchannel";
import { PiCrashError } from "~/harness/pi/errors";
import {
  extractAssistantText,
  humanizePiFailureReason,
  type PiAgentMessage,
  type PiEvent,
} from "~/harness/pi/rpc";
import {
  buildChildContentBlocks,
  parseSubagentCompletion,
  parseSubagentStart,
  type SubagentCompletion,
} from "~/harness/pi/subagent";
import {
  buildToolResultContent,
  extractTextFromToolPayload,
  FILE_CHANGE_TOOL_NAMES,
  mapPiToolCall,
} from "~/harness/pi/tool_rendering";

export type EmitFn = (message: Record<string, unknown>) => void;

interface ToolCallInfo {
  claudeName: string;
  claudeInput: Record<string, unknown>;
  assistantMessageId: string;
  partialText: string;
  isSubagent: boolean;
  isBackground: boolean;
}

export interface PiMultiplexerDeps {
  emit: EmitFn;
  promptId: string;
  // Whether an abort is expected this turn (interrupt pending / shutdown), so a
  // `stopReason:"aborted"` finalizes the partial instead of raising.
  isAbortExpected: () => boolean;
  // Called when the backchannel extension opens a dialog, with the
  // extension_ui_request id to answer (and the originating tool-call id).
  onPendingDialog: (uiRequestId: string) => void;
  onDiffNeeded?: () => void;
  // The extension paths pi was launched with (errors from these fail loud).
  loadedExtensionPaths?: readonly string[];
  now?: () => number;
}

function timestamp(now: () => number): string {
  return new Date(now()).toISOString();
}

function isBackchannelTool(name: string): boolean {
  return (
    name === ASK_USER_QUESTION_TOOL_NAME || name === EXIT_PLAN_MODE_TOOL_NAME
  );
}

// --- Out-of-band completion emitters (also used by the harness idle-drain) ---

export function emitBackgroundCompletion(
  emit: EmitFn,
  now: () => number,
  completion: BackgroundTaskCompletion,
): void {
  emit({
    object_type: "ResponseBlockAgentMessage",
    message_id: newAgentMessageId(),
    source: "AGENT",
    assistant_message_id: newAgentMessageId(),
    content: [makeTextBlock(formatBackgroundCompletion(completion))],
    parent_tool_use_id: null,
    approximate_creation_time: timestamp(now),
  });
  emit({
    object_type: "BackgroundTaskNotificationAgentMessage",
    message_id: newAgentMessageId(),
    source: "AGENT",
    background_task_id: completion.taskId,
    tool_use_id: completion.toolCallId,
    status: completion.status,
    summary: completion.summary,
    duration_seconds:
      completion.durationMs !== null ? completion.durationMs / 1000 : null,
    approximate_creation_time: timestamp(now),
  });
}

function formatSubagentCompletionText(completion: SubagentCompletion): string {
  const done = completion.children.filter((c) => c.status === "done").length;
  const failed = completion.children.filter((c) => c.status === "error").length;
  const total = completion.children.length;
  const verb =
    completion.status === "completed" ? "completed" : completion.status;
  return `Sub-agents ${verb}: ${done} done, ${failed} failed (of ${total}).`;
}

export function emitSubagentCompletion(
  emit: EmitFn,
  now: () => number,
  completion: SubagentCompletion,
): void {
  for (const child of completion.children) {
    emit({
      object_type: "ResponseBlockAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      assistant_message_id: newAgentMessageId(),
      content: buildChildContentBlocks(child, completion.toolCallId),
      parent_tool_use_id: completion.toolCallId,
      approximate_creation_time: timestamp(now),
    });
  }
  emit({
    object_type: "BackgroundTaskNotificationAgentMessage",
    message_id: newAgentMessageId(),
    source: "AGENT",
    background_task_id: completion.taskId,
    tool_use_id: completion.toolCallId,
    status: completion.status,
    summary: formatSubagentCompletionText(completion),
    duration_seconds: null,
    approximate_creation_time: timestamp(now),
  });
}

export class PiTurnMultiplexer {
  private accumulatedText = "";
  private assistantMessageId = newAgentMessageId();
  private firstMessageId = newAgentMessageId();
  private readonly toolCalls = new Map<string, ToolCallInfo>();
  private pendingBackchannelToolCallId: string | null = null;
  compactionOpen = false;

  constructor(private readonly deps: PiMultiplexerDeps) {}

  private get now(): () => number {
    return this.deps.now ?? Date.now;
  }

  private resetAccumulator(): void {
    this.accumulatedText = "";
    this.assistantMessageId = newAgentMessageId();
    this.firstMessageId = newAgentMessageId();
  }

  private emit(message: Record<string, unknown>): void {
    this.deps.emit(message);
  }

  private emitSimple(
    objectType: string,
    fields: Record<string, unknown> = {},
  ): void {
    this.emit({
      object_type: objectType,
      message_id: newAgentMessageId(),
      source: "AGENT",
      ...fields,
    });
  }

  private emitPartial(content: Block[]): void {
    this.emit({
      object_type: "PartialResponseBlockAgentMessage",
      message_id: newAgentMessageId(),
      source: "AGENT",
      content,
      assistant_message_id: this.assistantMessageId,
      first_response_message_id: this.firstMessageId,
      parent_tool_use_id: null,
      approximate_creation_time: timestamp(this.now),
    });
  }

  private emitResponseBlock(
    messageId: string,
    assistantMessageId: string,
    content: Block[],
  ): void {
    this.emit({
      object_type: "ResponseBlockAgentMessage",
      message_id: messageId,
      source: "AGENT",
      assistant_message_id: assistantMessageId,
      content,
      parent_tool_use_id: null,
      approximate_creation_time: timestamp(this.now),
    });
  }

  // Drive one parsed event; returns true when the turn ends (agent_end). Throws
  // PiCrashError on a failed turn.
  handleEvent(event: PiEvent): boolean {
    switch (event.kind) {
      case "response":
        if (
          event.command === "prompt" &&
          event.id === this.deps.promptId &&
          !event.success
        ) {
          throw new PiCrashError(
            event.error
              ? humanizePiFailureReason(event.error)
              : "pi rejected the prompt",
          );
        }
        return false;
      case "extension_ui_request":
        this.handleExtensionUiRequest(event);
        return false;
      case "agent_start":
        return false;
      case "message_update":
        this.handleMessageUpdate(event);
        return false;
      case "message_end":
        this.handleMessageEnd(event);
        return false;
      case "agent_end":
        return this.handleAgentEnd(event);
      case "tool_execution_start":
        this.handleToolExecutionStart(event);
        return false;
      case "tool_execution_update": {
        const info = this.toolCalls.get(event.toolCallId);
        if (info !== undefined) {
          info.partialText = extractTextFromToolPayload(event.partialResult);
        }
        return false;
      }
      case "tool_execution_end":
        this.handleToolExecutionEnd(event);
        return false;
      case "compaction_start":
        this.compactionOpen = true;
        this.emitSimple("AutoCompactingAgentMessage");
        return false;
      case "compaction_end":
        this.compactionOpen = false;
        this.emitSimple("AutoCompactingDoneAgentMessage");
        return false;
      case "auto_retry_end":
        if (!event.success) {
          throw new PiCrashError(
            humanizePiFailureReason(
              event.finalError ??
                this.accumulatedText ??
                "pi exhausted retries",
            ),
          );
        }
        return false;
      case "extension_error":
        if (
          (this.deps.loadedExtensionPaths ?? []).includes(event.extensionPath)
        ) {
          throw new PiCrashError(
            event.error || "the Sculptor backchannel extension raised an error",
          );
        }
        return false;
      case "unknown":
        return false;
    }
  }

  // Emit the stick-prevention AutoCompactingDone if a compaction was left open.
  finalize(): void {
    if (this.compactionOpen) {
      this.emitSimple("AutoCompactingDoneAgentMessage");
      this.compactionOpen = false;
    }
  }

  // --- Handlers -------------------------------------------------------------

  private handleMessageUpdate(
    event: Extract<PiEvent, { kind: "message_update" }>,
  ): void {
    const inner = event.assistantMessageEvent;
    if (inner.type === "text_delta") {
      const delta = typeof inner.delta === "string" ? inner.delta : "";
      if (!delta) {
        return;
      }
      this.accumulatedText += delta;
      this.emitPartial([makeTextBlock(this.accumulatedText)]);
      return;
    }
    if (inner.type === "error") {
      const reason =
        this.accumulatedText ||
        (typeof inner.reason === "string"
          ? inner.reason
          : "pi reported an in-stream error");
      throw new PiCrashError(humanizePiFailureReason(reason));
    }
  }

  private buildInterleavedContent(message: PiAgentMessage): Block[] {
    const blocks: Block[] = [];
    let sawTool = false;
    for (const raw of message.content) {
      if (raw.type === "text") {
        const text = raw.text;
        if (typeof text === "string" && text) {
          blocks.push(makeTextBlock(text));
        }
      } else if (raw.type === "toolCall") {
        const toolCallId = String(raw.id ?? raw.toolCallId ?? "");
        if (!toolCallId) {
          continue;
        }
        const piName = String(raw.name ?? raw.toolName ?? "");
        const piArgs =
          typeof raw.arguments === "object" && raw.arguments !== null
            ? (raw.arguments as Record<string, unknown>)
            : typeof raw.args === "object" && raw.args !== null
              ? (raw.args as Record<string, unknown>)
              : {};
        const { name, input } = mapPiToolCall(piName, piArgs);
        blocks.push(makeToolUseBlock(toolCallId, name, input));
        sawTool = true;
      }
    }
    if (!sawTool) {
      const finalText = extractAssistantText(message) || this.accumulatedText;
      return finalText ? [makeTextBlock(finalText)] : [];
    }
    return blocks;
  }

  private handleMessageEnd(
    event: Extract<PiEvent, { kind: "message_end" }>,
  ): void {
    const message = event.message;
    if (message.role !== "assistant") {
      return;
    }
    const stopReason = message.stopReason;
    if (
      stopReason === "error" ||
      (stopReason === "aborted" && !this.deps.isAbortExpected())
    ) {
      const reason =
        extractAssistantText(message) ||
        message.errorMessage ||
        this.accumulatedText;
      throw new PiCrashError(humanizePiFailureReason(reason));
    }
    const content = this.buildInterleavedContent(message);
    const hasToolBlocks = content.some((b) => b.object_type === "ToolUseBlock");
    if (hasToolBlocks) {
      this.emitPartial(content);
    }
    for (const block of content) {
      if (block.object_type === "ToolUseBlock") {
        const id = block.id as string;
        const name = block.name as string;
        this.toolCalls.set(id, {
          claudeName: name,
          claudeInput: (block.input ?? {}) as Record<string, unknown>,
          assistantMessageId: this.assistantMessageId,
          partialText: "",
          isSubagent: name === "Agent",
          isBackground: name === "background",
        });
        if (isBackchannelTool(name)) {
          this.pendingBackchannelToolCallId = id;
        }
      }
    }
    if (content.length > 0) {
      this.emitResponseBlock(
        this.firstMessageId,
        this.assistantMessageId,
        content,
      );
    }
    this.resetAccumulator();
  }

  private handleToolExecutionStart(
    event: Extract<PiEvent, { kind: "tool_execution_start" }>,
  ): void {
    const toolCallId = event.toolCallId;
    if (!toolCallId || this.toolCalls.has(toolCallId)) {
      return;
    }
    const { name, input } = mapPiToolCall(event.toolName, event.args);
    this.toolCalls.set(toolCallId, {
      claudeName: name,
      claudeInput: input,
      assistantMessageId: this.assistantMessageId,
      partialText: "",
      isSubagent: name === "Agent",
      isBackground: name === "background",
    });
    const textBlocks: Block[] = this.accumulatedText
      ? [makeTextBlock(this.accumulatedText)]
      : [];
    this.emitPartial([
      ...textBlocks,
      makeToolUseBlock(toolCallId, name, input),
    ]);
  }

  private handleToolExecutionEnd(
    event: Extract<PiEvent, { kind: "tool_execution_end" }>,
  ): void {
    const info = this.toolCalls.get(event.toolCallId);
    // Refresh the workspace diff after a successful file-mutating tool.
    if (
      info !== undefined &&
      FILE_CHANGE_TOOL_NAMES.has(info.claudeName) &&
      !event.isError
    ) {
      this.deps.onDiffNeeded?.();
    }
    if (!event.toolCallId) {
      return;
    }
    let toolName: string;
    let toolInput: Record<string, unknown>;
    let assistantMessageId: string;
    let fallbackText: string;
    if (info !== undefined) {
      toolName = info.claudeName;
      toolInput = info.claudeInput;
      assistantMessageId = info.assistantMessageId;
      fallbackText = info.partialText;
      if (info.isSubagent) {
        this.emitSubagentStarted(event.result, event.toolCallId);
      }
      if (info.isBackground) {
        this.emitBackgroundStarted(event.result, event.toolCallId);
      }
    } else {
      const mapped = mapPiToolCall(event.toolName, {});
      toolName = mapped.name;
      toolInput = mapped.input;
      assistantMessageId = this.assistantMessageId;
      fallbackText = "";
    }
    const resultBlock = makeToolResultBlock({
      toolUseId: event.toolCallId,
      toolName,
      invocationString: getToolInvocationString(toolName, toolInput),
      content: buildToolResultContent(
        toolName,
        toolInput,
        event.result,
        fallbackText,
      ),
      isError: event.isError,
      description: null,
    });
    this.emitResponseBlock(newAgentMessageId(), assistantMessageId, [
      resultBlock,
    ]);
  }

  private emitSubagentStarted(
    resultPayload: unknown,
    parentToolCallId: string,
  ): void {
    const started = parseSubagentStart(resultPayload);
    if (started === null) {
      return;
    }
    this.emitSimple("BackgroundTaskStartedAgentMessage", {
      background_task_id: started.taskId,
      tool_use_id: started.toolCallId || parentToolCallId,
      description: started.count
        ? `${started.count} sub-agent(s)`
        : started.label,
      task_type: started.label,
    });
  }

  private emitBackgroundStarted(
    resultPayload: unknown,
    parentToolCallId: string,
  ): void {
    const started = parseBackgroundStart(resultPayload);
    if (started === null) {
      return;
    }
    this.emitSimple("BackgroundTaskStartedAgentMessage", {
      background_task_id: started.taskId,
      tool_use_id: started.toolCallId || parentToolCallId,
      description: started.command || started.label,
      task_type: started.label,
    });
  }

  private handleAgentEnd(
    event: Extract<PiEvent, { kind: "agent_end" }>,
  ): boolean {
    const abortExpected = this.deps.isAbortExpected();
    for (const message of event.messages) {
      if (
        message.role !== "assistant" ||
        (message.stopReason !== "error" && message.stopReason !== "aborted")
      ) {
        continue;
      }
      if (message.stopReason === "aborted" && abortExpected) {
        continue;
      }
      const reason =
        extractAssistantText(message) ||
        message.errorMessage ||
        this.accumulatedText;
      throw new PiCrashError(humanizePiFailureReason(reason));
    }
    if (this.accumulatedText) {
      this.emitResponseBlock(this.firstMessageId, this.assistantMessageId, [
        makeTextBlock(this.accumulatedText),
      ]);
    }
    return true;
  }

  private handleExtensionUiRequest(
    event: Extract<PiEvent, { kind: "extension_ui_request" }>,
  ): void {
    if (event.method === "notify") {
      const background = parseBackgroundCompletion(event.message);
      if (background !== null) {
        emitBackgroundCompletion(this.deps.emit, this.now, background);
        return;
      }
      const subagent = parseSubagentCompletion(event.message);
      if (subagent !== null) {
        emitSubagentCompletion(this.deps.emit, this.now, subagent);
        return;
      }
      return;
    }
    if (event.method !== "select" && event.method !== "input") {
      return;
    }
    const questionData = this.buildQuestionData(event);
    this.deps.onPendingDialog(event.id);
    this.emitSimple("AskUserQuestionAgentMessage", {
      question_data: questionData,
    });
  }

  private buildQuestionData(
    event: Extract<PiEvent, { kind: "extension_ui_request" }>,
  ): AskUserQuestionData {
    const toolUseId = this.pendingBackchannelToolCallId ?? event.id;
    if (
      event.method === "select" &&
      event.title === PLAN_APPROVAL_DIALOG_TITLE
    ) {
      return makePlanApprovalQuestion(toolUseId);
    }
    return buildAskUserQuestionData(
      event.title ?? "",
      event.options ?? [],
      toolUseId,
    );
  }
}
