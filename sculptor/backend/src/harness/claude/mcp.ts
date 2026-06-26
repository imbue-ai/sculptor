// In-process MCP server for Sculptor's `mcp__sculptor__ask_user_question` and
// `mcp__sculptor__exit_plan_mode` tools. Ports `mcp_server.py`, `mcp_schemas.py`,
// and `mcp_result_formatters.py`.
//
// The Claude CLI registers this server via `--mcp-config` and routes all
// `tools/call` invocations back as `control_request` envelopes with
// `subtype == "mcp_message"`. We dispatch by JSON-RPC method, hold `tools/call`
// requests against a registry keyed by Claude's `tool_use_id`, and resolve them
// via `deliverAnswer` when the user answers in the UI.

import {
  JSONRPC_INVALID_PARAMS,
  JSONRPC_INVALID_REQUEST,
  JSONRPC_METHOD_NOT_FOUND,
  MCP_ASK_TOOL_FQN,
  MCP_ASK_TOOL_NAME,
  MCP_EXIT_PLAN_MODE_TOOL_FQN,
  MCP_EXIT_PLAN_MODE_TOOL_NAME,
  MCP_PROTOCOL_VERSION,
  MCP_SERVER_NAME,
  MCP_SERVER_VERSION,
} from "~/harness/claude/constants";

// --- Answer message shape -------------------------------------------------

export interface UserQuestionOption {
  label: string;
  description: string;
}

export interface UserQuestion {
  question: string;
  header: string;
  options: UserQuestionOption[];
  multi_select?: boolean;
  other_label?: string | null;
}

export interface AskUserQuestionData {
  questions: UserQuestion[];
  tool_use_id: string;
  plan_file_path?: string | null;
}

// The UI's answer to an MCP-held question (the relevant fields of the Python
// `UserQuestionAnswerMessage`).
export interface UserQuestionAnswer {
  message_id: string;
  tool_use_id: string;
  question_data: AskUserQuestionData;
  answers: Record<string, string>;
  notes: Record<string, string>;
}

// --- Schemas (tools/list) -------------------------------------------------

function buildAskUserQuestionTool(
  askToolName: string,
): Record<string, unknown> {
  return {
    name: askToolName,
    description:
      "Ask the user one or more multiple-choice questions with optional freeform text. Use when you need user input to proceed: clarifying ambiguous requirements, confirming destructive actions, choosing between implementation approaches. Do NOT use for conversational replies — just respond in chat. Prefer this over plain-text prompts when there is a discrete set of options.",
    inputSchema: {
      type: "object",
      required: ["questions"],
      properties: {
        questions: {
          type: "array",
          minItems: 1,
          maxItems: 4,
          items: {
            type: "object",
            required: ["question", "header", "options", "multiSelect"],
            properties: {
              question: { type: "string" },
              header: { type: "string" },
              options: {
                type: "array",
                minItems: 2,
                maxItems: 10,
                items: {
                  type: "object",
                  required: ["label", "description"],
                  properties: {
                    label: { type: "string" },
                    description: { type: "string" },
                  },
                },
              },
              multiSelect: { type: "boolean" },
            },
          },
        },
      },
    },
  };
}

function buildExitPlanModeTool(
  exitPlanModeToolName: string,
): Record<string, unknown> {
  return {
    name: exitPlanModeToolName,
    description:
      "Present your implementation plan to the user for approval before executing it. Call this only when you have written your plan to the plan file specified in the plan-mode system reminder. The user will approve, request revisions, or dismiss. Do NOT call this for open-ended brainstorming.",
    inputSchema: { type: "object", properties: {} },
  };
}

export function buildMcpTools(): Record<string, unknown>[] {
  return [
    buildAskUserQuestionTool(MCP_ASK_TOOL_NAME),
    buildExitPlanModeTool(MCP_EXIT_PLAN_MODE_TOOL_NAME),
  ];
}

// --- Argument validation --------------------------------------------------

const MIN_QUESTIONS = 1;
const MAX_QUESTIONS = 4;
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 10;

function isQuestionShape(value: unknown): boolean {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const q = value as Record<string, unknown>;
  if (typeof q.question !== "string" || typeof q.header !== "string") {
    return false;
  }
  if (typeof q.multiSelect !== "boolean") {
    return false;
  }
  if (!Array.isArray(q.options)) {
    return false;
  }
  for (const option of q.options) {
    if (typeof option !== "object" || option === null) {
      return false;
    }
    const o = option as Record<string, unknown>;
    if (typeof o.label !== "string" || typeof o.description !== "string") {
      return false;
    }
  }
  return true;
}

// Mirrors `mcp_server._validate_arguments`. Returns null if valid, else a
// human-readable error string forwarded to the agent in the JSON-RPC error.
export function validateArguments(
  toolFqn: string,
  args: unknown,
): string | null {
  if (typeof args !== "object" || args === null || Array.isArray(args)) {
    return `Invalid params: 'arguments' must be an object, got ${typeof args}`;
  }
  if (toolFqn !== MCP_ASK_TOOL_FQN) {
    return null;
  }
  const argsObj = args as Record<string, unknown>;
  if (!("questions" in argsObj)) {
    return "Invalid params: missing required field 'questions'";
  }
  const questions = argsObj.questions;
  if (!Array.isArray(questions)) {
    return `Invalid params: 'questions' must be an array, got ${typeof questions}`;
  }
  if (questions.length < MIN_QUESTIONS || questions.length > MAX_QUESTIONS) {
    return `Invalid params: 'questions' must contain ${MIN_QUESTIONS}-${MAX_QUESTIONS} items, got ${questions.length}`;
  }
  for (const question of questions) {
    if (typeof question === "object" && question !== null) {
      const options = (question as Record<string, unknown>).options;
      if (
        Array.isArray(options) &&
        (options.length < MIN_OPTIONS || options.length > MAX_OPTIONS)
      ) {
        return `Invalid params: each question's 'options' must contain ${MIN_OPTIONS}-${MAX_OPTIONS} items, got ${options.length}`;
      }
    }
    if (!isQuestionShape(question)) {
      return "Invalid params for 'questions': question does not match the required schema";
    }
  }
  return null;
}

// --- Result formatters ----------------------------------------------------

const AUQ_DISMISSED_TEXT =
  "User dismissed the question(s) without answering. Stop and wait for the user to provide further instructions before taking any more actions.";
const DISMISSED_ANSWER_VALUE = "[Dismissed]";
const PLAN_APPROVED_TEXT =
  "User has approved your plan. You can now start coding. Start with updating your todo list if applicable";
const PLAN_REJECTED_FIRST_LINE =
  "The agent proposed a plan that was rejected by the user. The user chose to stay in plan mode rather than proceed with implementation.";
const PLAN_DISMISSED_TEXT =
  "User dismissed the plan approval without responding. Stop and wait for the user to provide further instructions before taking any more actions.";
const PLAN_APPROVAL_HEADER = "Plan approval";
const PLAN_APPROVE_ANSWER = "Approve plan";

export function isPlanApprovalQuestion(answer: UserQuestionAnswer): boolean {
  return answer.question_data.questions.some(
    (q) => q.header === PLAN_APPROVAL_HEADER,
  );
}

export function isPlanApproval(answer: UserQuestionAnswer): boolean {
  if (!isPlanApprovalQuestion(answer)) {
    return false;
  }
  return Object.values(answer.answers).some(
    (v) => v.trim() === PLAN_APPROVE_ANSWER,
  );
}

export function formatAskUserQuestionResult(
  answer: UserQuestionAnswer,
): string {
  const parts: string[] = [];
  for (const question of answer.question_data.questions) {
    const answerValue = answer.answers[question.question] ?? "";
    if (!answerValue || answerValue === DISMISSED_ANSWER_VALUE) {
      continue;
    }
    const subParts = [`"${question.question}"="${answerValue}"`];
    const notesValue = answer.notes[question.question] ?? "";
    if (notesValue) {
      subParts.push(`user notes: ${notesValue}`);
    }
    parts.push(subParts.join(" "));
  }
  if (parts.length === 0) {
    return AUQ_DISMISSED_TEXT;
  }
  return `User has answered your questions: ${parts.join(", ")}. You can now continue with the user's answers in mind.`;
}

export function formatExitPlanModeResult(answer: UserQuestionAnswer): string {
  if (isPlanApproval(answer)) {
    return PLAN_APPROVED_TEXT;
  }
  let feedback = "";
  let isDismissed = false;
  for (const question of answer.question_data.questions) {
    const answerValue = (answer.answers[question.question] ?? "").trim();
    if (answerValue === DISMISSED_ANSWER_VALUE) {
      isDismissed = true;
      continue;
    }
    if (answerValue) {
      feedback = answerValue;
    }
  }
  if (isDismissed && !feedback) {
    return PLAN_DISMISSED_TEXT;
  }
  if (feedback) {
    return `${PLAN_REJECTED_FIRST_LINE}\nUser feedback on this plan: ${feedback}`;
  }
  return PLAN_REJECTED_FIRST_LINE;
}

// --- The server -----------------------------------------------------------

// Sends the response payload for a control_request back to the CLI on stdin.
export type McpRespond = (
  controlRequestId: string,
  responseData: Record<string, unknown>,
) => void;

interface PendingCall {
  controlRequestId: string;
  mcpMessageId: number | string;
  toolFqn: string;
  toolUseId: string;
}

export class SculptorMcpServer {
  private respond: McpRespond;
  private readonly pending = new Map<string, PendingCall>();
  // Cache of the most recently delivered answer text, served back for a
  // duplicate `tools/call` within the same Q&A (the resumed CLI re-emits the
  // dangling call with a fresh tool_use_id). Invalidated when a fresh AUQ panel
  // is shown via `registerToolUseId`.
  private lastDeliveredText: string | null = null;
  private hasNewAuqSinceLastDelivery = false;
  private expectedToolUseId: string | null = null;

  constructor(respond: McpRespond) {
    this.respond = respond;
  }

  setRespond(respond: McpRespond): void {
    this.respond = respond;
  }

  // Inform the server that a `tools/call` for `toolUseId` is imminent (called
  // when an assistant stream surfaces a Sculptor MCP ToolUseBlock).
  registerToolUseId(toolUseId: string, toolFqn: string): void {
    if (
      toolFqn !== MCP_ASK_TOOL_FQN &&
      toolFqn !== MCP_EXIT_PLAN_MODE_TOOL_FQN
    ) {
      return;
    }
    this.expectedToolUseId = toolUseId;
    if (this.lastDeliveredText !== null) {
      this.hasNewAuqSinceLastDelivery = true;
    }
  }

  hasPendingCall(toolUseId: string): boolean {
    return this.pending.has(toolUseId);
  }

  // Dispatch an MCP JSON-RPC message (the `message` of an mcp_message envelope).
  handleMessage(
    controlRequestId: string,
    message: Record<string, unknown>,
  ): void {
    const method = message.method;
    if (method === "initialize") {
      this.respondResult(controlRequestId, message, {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: { name: MCP_SERVER_NAME, version: MCP_SERVER_VERSION },
      });
    } else if (method === "tools/list") {
      this.respondResult(controlRequestId, message, { tools: buildMcpTools() });
    } else if (method === "tools/call") {
      this.handleToolsCall(controlRequestId, message);
    } else if (method === "notifications/initialized") {
      this.respondResult(controlRequestId, message, {});
    } else {
      this.respondError(
        controlRequestId,
        message,
        JSONRPC_METHOD_NOT_FOUND,
        `Unknown method: ${String(method)}`,
      );
    }
  }

  // Resolve the held `tools/call` for `answer.tool_use_id`.
  deliverAnswer(answer: UserQuestionAnswer): void {
    const pending = this.pending.get(answer.tool_use_id);
    if (pending === undefined) {
      return;
    }
    this.pending.delete(answer.tool_use_id);
    const text = this.formatAnswerText(pending.toolFqn, answer);
    this.lastDeliveredText = text;
    this.hasNewAuqSinceLastDelivery = false;
    this.respondWithText(pending.controlRequestId, pending.mcpMessageId, text);
  }

  private handleToolsCall(
    controlRequestId: string,
    message: Record<string, unknown>,
  ): void {
    const params = (message.params ?? {}) as Record<string, unknown>;
    const toolNameShort = params.name;
    let toolFqn: string;
    if (toolNameShort === MCP_ASK_TOOL_NAME) {
      toolFqn = MCP_ASK_TOOL_FQN;
    } else if (toolNameShort === MCP_EXIT_PLAN_MODE_TOOL_NAME) {
      toolFqn = MCP_EXIT_PLAN_MODE_TOOL_FQN;
    } else {
      this.respondError(
        controlRequestId,
        message,
        JSONRPC_INVALID_PARAMS,
        `Invalid params: unknown tool ${JSON.stringify(toolNameShort)}`,
      );
      return;
    }

    const validationError = validateArguments(toolFqn, params.arguments ?? {});
    if (validationError !== null) {
      this.respondError(
        controlRequestId,
        message,
        JSONRPC_INVALID_PARAMS,
        validationError,
      );
      return;
    }

    const toolUseId = this.expectedToolUseId;
    this.expectedToolUseId = null;
    const cachedText =
      this.lastDeliveredText !== null && !this.hasNewAuqSinceLastDelivery
        ? this.lastDeliveredText
        : null;

    if (cachedText !== null) {
      this.respondWithText(
        controlRequestId,
        message.id as number | string,
        cachedText,
      );
      return;
    }
    if (toolUseId === null) {
      // No registered tool_use_id (out-of-order assistant stream) and no cached
      // answer. Dropping it silently would leave the CLI blocked forever on a
      // tools/call that can never be matched to a UI panel, wedging the turn
      // until it's killed. Unblock it with a tool-error result so the agent can
      // continue instead.
      this.respondWithErrorText(
        controlRequestId,
        message.id as number | string,
        "This question could not be presented to the user. Continue without it.",
      );
      return;
    }
    this.pending.set(toolUseId, {
      controlRequestId,
      mcpMessageId: message.id as number | string,
      toolFqn,
      toolUseId,
    });
  }

  private formatAnswerText(
    toolFqn: string,
    answer: UserQuestionAnswer,
  ): string {
    if (toolFqn === MCP_EXIT_PLAN_MODE_TOOL_FQN) {
      return formatExitPlanModeResult(answer);
    }
    return formatAskUserQuestionResult(answer);
  }

  private respondResult(
    controlRequestId: string,
    message: Record<string, unknown>,
    result: Record<string, unknown>,
  ): void {
    this.respond(controlRequestId, {
      mcp_response: { jsonrpc: "2.0", id: message.id, result },
    });
  }

  private respondError(
    controlRequestId: string,
    message: Record<string, unknown>,
    code: number,
    errorMessage: string,
  ): void {
    this.respond(controlRequestId, {
      mcp_response: {
        jsonrpc: "2.0",
        id: message.id,
        error: { code, message: errorMessage },
      },
    });
  }

  private respondWithText(
    controlRequestId: string,
    mcpMessageId: number | string,
    text: string,
  ): void {
    this.respond(controlRequestId, {
      mcp_response: {
        jsonrpc: "2.0",
        id: mcpMessageId,
        result: { content: [{ type: "text", text }], isError: false },
      },
    });
  }

  // A successful JSON-RPC result whose tool payload is flagged as an error, used
  // to unblock a tools/call we cannot route to a UI panel.
  private respondWithErrorText(
    controlRequestId: string,
    mcpMessageId: number | string,
    text: string,
  ): void {
    this.respond(controlRequestId, {
      mcp_response: {
        jsonrpc: "2.0",
        id: mcpMessageId,
        result: { content: [{ type: "text", text }], isError: true },
      },
    });
  }

  // Respond to an mcp_message for an unknown/disabled server.
  respondUnknownServer(controlRequestId: string, messageId: unknown): void {
    this.respond(controlRequestId, {
      mcp_response: {
        jsonrpc: "2.0",
        id: messageId,
        error: { code: JSONRPC_INVALID_REQUEST, message: "Unknown MCP server" },
      },
    });
  }
}
