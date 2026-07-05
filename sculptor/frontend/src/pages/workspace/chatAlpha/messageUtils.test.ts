import { describe, expect, it } from "vitest";

import type { ChatMessage } from "~/api";

import { getPlainText, getToolResultSummary, getToolUseSummary } from "./messageUtils.ts";

const makeMessage = (content: ReadonlyArray<Record<string, unknown>>): ChatMessage =>
  ({
    id: "msg-test",
    role: "assistant",
    content,
    approximateCreationTime: new Date().toISOString(),
  }) as unknown as ChatMessage;

describe("getPlainText", () => {
  it("returns empty string for message with no text blocks", () => {
    const message = makeMessage([{ type: "tool_use", id: "t1", name: "Bash", input: {} }]);
    expect(getPlainText(message)).toBe("");
  });

  it("returns text from a single text block", () => {
    const message = makeMessage([{ type: "text", text: "Hello world" }]);
    expect(getPlainText(message)).toBe("Hello world");
  });

  it("concatenates multiple text blocks", () => {
    const message = makeMessage([
      { type: "text", text: "Part one. " },
      { type: "text", text: "Part two." },
    ]);
    expect(getPlainText(message)).toBe("Part one. Part two.");
  });

  it("ignores non-text blocks interspersed with text blocks", () => {
    const message = makeMessage([
      { type: "text", text: "Before tool. " },
      { type: "tool_use", id: "t1", name: "Read", input: {} },
      { type: "text", text: "After tool." },
    ]);
    expect(getPlainText(message)).toBe("Before tool. After tool.");
  });

  it("returns empty string for empty content array", () => {
    const message = makeMessage([]);
    expect(getPlainText(message)).toBe("");
  });
});

describe("getToolUseSummary", () => {
  it("returns empty array for message with no tool_use blocks", () => {
    const message = makeMessage([{ type: "text", text: "Just text" }]);
    expect(getToolUseSummary(message)).toEqual([]);
  });

  it("summarizes a single tool_use block", () => {
    const message = makeMessage([{ type: "tool_use", id: "tu-1", name: "Bash", input: { command: "ls" } }]);
    expect(getToolUseSummary(message)).toEqual(["Bash(id: tu-1)"]);
  });

  it("summarizes multiple tool_use blocks", () => {
    const message = makeMessage([
      { type: "tool_use", id: "tu-1", name: "Read", input: {} },
      { type: "tool_use", id: "tu-2", name: "Edit", input: {} },
    ]);
    expect(getToolUseSummary(message)).toEqual(["Read(id: tu-1)", "Edit(id: tu-2)"]);
  });

  it("skips non-tool_use blocks", () => {
    const message = makeMessage([
      { type: "text", text: "Hello" },
      { type: "tool_use", id: "tu-1", name: "Bash", input: {} },
    ]);
    expect(getToolUseSummary(message)).toEqual(["Bash(id: tu-1)"]);
  });
});

describe("getToolResultSummary", () => {
  it("returns empty array for message with no tool_result blocks", () => {
    const message = makeMessage([{ type: "text", text: "Just text" }]);
    expect(getToolResultSummary(message)).toEqual([]);
  });

  it("summarizes a single tool_result block", () => {
    const message = makeMessage([
      { type: "tool_result", toolUseId: "tu-1", toolName: "Bash", content: { contentType: "generic", text: "output" } },
    ]);
    expect(getToolResultSummary(message)).toEqual(["Bash (toolUseId: tu-1)"]);
  });

  it("summarizes multiple tool_result blocks", () => {
    const message = makeMessage([
      {
        type: "tool_result",
        toolUseId: "tu-1",
        toolName: "Read",
        content: { contentType: "generic", text: "file contents" },
      },
      {
        type: "tool_result",
        toolUseId: "tu-2",
        toolName: "Bash",
        content: { contentType: "generic", text: "ok" },
      },
    ]);
    expect(getToolResultSummary(message)).toEqual(["Read (toolUseId: tu-1)", "Bash (toolUseId: tu-2)"]);
  });

  it("skips non-tool_result blocks", () => {
    const message = makeMessage([
      { type: "tool_use", id: "tu-1", name: "Read", input: {} },
      {
        type: "tool_result",
        toolUseId: "tu-1",
        toolName: "Read",
        content: { contentType: "generic", text: "data" },
      },
    ]);
    expect(getToolResultSummary(message)).toEqual(["Read (toolUseId: tu-1)"]);
  });
});
