/**
 * Low-level builders for constructing ChatMessage fixtures.
 *
 * These builders produce typed-enough objects for Storybook and tests without
 * requiring every field that the generated ChatMessage type demands. The
 * `as unknown as ChatMessage` cast at the end of each builder keeps the call
 * sites clean while still giving consumers the real type.
 *
 * Usage:
 *   import { msg, blocks } from "./messageBuilders.ts";
 *   const messages = [
 *     msg.user("Can you help?"),
 *     msg.assistant([blocks.text("Sure!"), blocks.toolUse("Read", { file_path: "foo.ts" })]),
 *   ];
 */

import type { ChatMessage } from "~/api";
import { ChatMessageRole } from "~/api";

const BASE_TIME = new Date("2026-03-09T14:30:00.000Z");
const TIMESTAMP_STEP_MS = 1_500;
let offsetCounter = 0;

/** Return an ISO timestamp offset from BASE_TIME by `ms` milliseconds. */
export const ts = (ms: number): string => new Date(BASE_TIME.getTime() + ms).toISOString();

/** Return the next auto-incrementing timestamp, advancing by TIMESTAMP_STEP_MS each call. */
const nextTs = (): string => {
  const t = ts(offsetCounter);
  offsetCounter += TIMESTAMP_STEP_MS;
  return t;
};

let toolIdCounter = 0;

const nextToolId = (): string => `tool-${String(++toolIdCounter).padStart(3, "0")}`;

export const blocks = {
  text: (text: string): { type: "text"; text: string } => ({ type: "text", text }),

  toolUse: (
    name: string,
    input: Record<string, unknown> = {},
    id?: string,
  ): { type: "tool_use"; id: string; name: string; input: Record<string, unknown> } => ({
    type: "tool_use",
    id: id ?? nextToolId(),
    name,
    input,
  }),

  toolResult: (
    toolUseId: string,
    toolName: string,
    content: string,
    isError = false,
  ): { type: "tool_result"; toolUseId: string; toolName: string; content: string; isError: boolean } => ({
    type: "tool_result",
    toolUseId,
    toolName,
    content,
    isError,
  }),

  error: (
    message: string,
    errorType = "Error",
    traceback?: string,
  ): { type: "error"; message: string; errorType: string; traceback?: string } => ({
    type: "error",
    message,
    errorType,
    ...(traceback != null ? { traceback } : {}),
  }),

  warning: (message: string, warningType = "general"): { type: "warning"; message: string; warningType: string } => ({
    type: "warning",
    message,
    warningType,
  }),

  contextSummary: (text: string): { type: "context_summary"; text: string } => ({
    type: "context_summary",
    text,
  }),

  contextCleared: (): { type: "context_cleared" } => ({ type: "context_cleared" }),

  resumeResponse: (): { type: "resume_response" } => ({ type: "resume_response" }),

  file: (source: string): { type: "file"; source: string } => ({ type: "file", source }),
};

let msgIdCounter = 0;

const nextMsgId = (): string => `msg-${String(++msgIdCounter).padStart(3, "0")}`;

type BlockLike = ReturnType<(typeof blocks)[keyof typeof blocks]>;

export const msg = {
  /** User message from a single text string. */
  user: (text: string, overrides?: Partial<ChatMessage>): ChatMessage =>
    ({
      role: ChatMessageRole.USER,
      id: nextMsgId(),
      content: [blocks.text(text)],
      approximateCreationTime: nextTs(),
      ...overrides,
    }) as unknown as ChatMessage,

  /** Assistant message from a list of content blocks. */
  assistant: (content: ReadonlyArray<BlockLike>, overrides?: Partial<ChatMessage>): ChatMessage =>
    ({
      role: ChatMessageRole.ASSISTANT,
      id: nextMsgId(),
      content,
      approximateCreationTime: nextTs(),
      ...overrides,
    }) as unknown as ChatMessage,

  /** Assistant text-only shorthand. */
  assistantText: (text: string, overrides?: Partial<ChatMessage>): ChatMessage =>
    ({
      role: ChatMessageRole.ASSISTANT,
      id: nextMsgId(),
      content: [blocks.text(text)],
      approximateCreationTime: nextTs(),
      ...overrides,
    }) as unknown as ChatMessage,
};

/** Reset all counters. Call at the top of each scenario function. */
export const resetCounters = (): void => {
  offsetCounter = 0;
  toolIdCounter = 0;
  msgIdCounter = 0;
};
