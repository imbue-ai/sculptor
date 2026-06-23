import { describe, expect, it } from "vitest";

import type { ChatMessage } from "~/api";
import { ChatMessageRole } from "~/api";

import { extractSearchableText, findMatches, splitMarkdownSegments } from "../alphaSearchUtils.ts";

const makeTextBlock = (text: string): { type: "text"; text: string } => ({ type: "text", text });

const makeToolUseBlock = (): { type: "tool_use"; id: string; name: string; input: Record<string, unknown> } => ({
  type: "tool_use",
  id: "tool-1",
  name: "TestTool",
  input: { query: "hello" },
});

const makeToolResultBlock = (): { type: "tool_result"; tool_use_id: string; content: string } => ({
  type: "tool_result",
  tool_use_id: "tool-1",
  content: "result text",
});

const makeMessage = (id: string, content: Array<unknown>): ChatMessage =>
  ({
    id,
    role: ChatMessageRole.ASSISTANT,
    content,
  }) as unknown as ChatMessage;

describe("splitMarkdownSegments", () => {
  it("returns single text segment for plain text", () => {
    expect(splitMarkdownSegments("Hello world")).toEqual([{ text: "Hello world", type: "text" }]);
  });

  it("splits fenced code blocks from surrounding text", () => {
    const md = "Before\n\n```python\nprint('hi')\n```\n\nAfter";
    const segments = splitMarkdownSegments(md);
    expect(segments).toEqual([
      { text: "Before\n\n", type: "text" },
      { text: "print('hi')\n", type: "code" },
      { text: "\n\nAfter", type: "text" },
    ]);
  });

  it("excludes language identifier from code content", () => {
    const md = "```python\ncode here\n```";
    const segments = splitMarkdownSegments(md);
    expect(segments).toEqual([{ text: "code here\n", type: "code" }]);
  });

  it("handles tilde fences", () => {
    const md = "~~~js\nalert(1)\n~~~";
    const segments = splitMarkdownSegments(md);
    expect(segments).toEqual([{ text: "alert(1)\n", type: "code" }]);
  });

  it("handles multiple code blocks", () => {
    const md = "Text\n\n```\nblock1\n```\n\nMiddle\n\n```\nblock2\n```\n\nEnd";
    const segments = splitMarkdownSegments(md);
    expect(segments).toHaveLength(5);
    expect(segments[0]).toEqual({ text: "Text\n\n", type: "text" });
    expect(segments[1]).toEqual({ text: "block1\n", type: "code" });
    expect(segments[2]).toEqual({ text: "\n\nMiddle\n\n", type: "text" });
    expect(segments[3]).toEqual({ text: "block2\n", type: "code" });
    expect(segments[4]).toEqual({ text: "\n\nEnd", type: "text" });
  });

  it("returns original text when no fences are present", () => {
    expect(splitMarkdownSegments("no code here")).toEqual([{ text: "no code here", type: "text" }]);
  });
});

describe("extractSearchableText", () => {
  it("extracts text blocks", () => {
    const message = makeMessage("1", [makeTextBlock("Hello world"), makeTextBlock("Goodbye")]);
    const result = extractSearchableText(message);
    expect(result).toEqual([
      { blockIndex: 0, text: "Hello world", type: "text" },
      { blockIndex: 1, text: "Goodbye", type: "text" },
    ]);
  });

  it("splits code fences into separate segments", () => {
    const md = "Text\n\n```python\ncode()\n```\n\nMore text";
    const message = makeMessage("1", [makeTextBlock(md)]);
    const result = extractSearchableText(message);
    expect(result).toHaveLength(3);
    expect(result[0].type).toBe("text");
    expect(result[1]).toEqual({ blockIndex: 0, text: "code()\n", type: "code" });
    expect(result[2].type).toBe("text");
  });

  it("skips tool use blocks", () => {
    const message = makeMessage("1", [makeTextBlock("Hello"), makeToolUseBlock()]);
    const result = extractSearchableText(message);
    expect(result).toHaveLength(1);
    expect(result[0].text).toBe("Hello");
  });

  it("skips tool result blocks", () => {
    const message = makeMessage("1", [makeToolResultBlock(), makeTextBlock("After tool")]);
    const result = extractSearchableText(message);
    expect(result).toHaveLength(1);
    expect(result[0].text).toBe("After tool");
  });

  it("returns empty array for message with only tool blocks", () => {
    const message = makeMessage("1", [makeToolUseBlock(), makeToolResultBlock()]);
    const result = extractSearchableText(message);
    expect(result).toHaveLength(0);
  });
});

describe("findMatches", () => {
  it("finds case-insensitive matches", () => {
    const messages = [makeMessage("1", [makeTextBlock("Hello World hello")])];
    const matches = findMatches(messages, "hello");
    expect(matches).toHaveLength(2);
    expect(matches[0]).toEqual({
      messageId: "1",
      messageIndex: 0,
      blockIndex: 0,
      startOffset: 0,
      length: 5,
    });
    expect(matches[1].startOffset).toBe(12);
  });

  it("returns empty for no matches", () => {
    const messages = [makeMessage("1", [makeTextBlock("Hello World")])];
    const matches = findMatches(messages, "xyz");
    expect(matches).toHaveLength(0);
  });

  it("returns empty for empty query", () => {
    const messages = [makeMessage("1", [makeTextBlock("Hello World")])];
    const matches = findMatches(messages, "");
    expect(matches).toHaveLength(0);
  });

  it("finds multiple matches within same block", () => {
    const messages = [makeMessage("1", [makeTextBlock("aaa")])];
    const matches = findMatches(messages, "a");
    expect(matches).toHaveLength(3);
  });

  it("advances cursor by query length, not by 1, for self-overlapping queries", () => {
    // Regression: the cursor advanced by 1 instead of the query length, so a
    // self-overlapping query produced overlapping matches. "aa" in "aaaa" must
    // yield non-overlapping matches at offsets 0 and 2 (two matches); the bug
    // produced three overlapping matches at offsets 0, 1, and 2.
    const messages = [makeMessage("1", [makeTextBlock("aaaa")])];
    const matches = findMatches(messages, "aa");
    expect(matches).toHaveLength(2);
    expect(matches.map((m) => m.startOffset)).toEqual([0, 2]);
  });

  it("finds matches across multiple messages", () => {
    const messages = [makeMessage("1", [makeTextBlock("Hello")]), makeMessage("2", [makeTextBlock("hello again")])];
    const matches = findMatches(messages, "hello");
    expect(matches).toHaveLength(2);
    expect(matches[0].messageId).toBe("1");
    expect(matches[1].messageId).toBe("2");
  });

  it("skips tool blocks when searching", () => {
    const messages = [makeMessage("1", [makeTextBlock("hello"), makeToolUseBlock()])];
    // The tool use block has "hello" in its input, but should not be searched
    const matches = findMatches(messages, "hello");
    expect(matches).toHaveLength(1);
    expect(matches[0].blockIndex).toBe(0);
  });

  it("tracks correct blockIndex for non-contiguous blocks", () => {
    const messages = [makeMessage("1", [makeToolUseBlock(), makeTextBlock("hello")])];
    const matches = findMatches(messages, "hello");
    expect(matches).toHaveLength(1);
    expect(matches[0].blockIndex).toBe(1);
  });

  it("excludes matches in code fence markers", () => {
    // "python" appears in the fence marker but NOT in the code content
    const md = "```python\nprint('hi')\n```";
    const messages = [makeMessage("1", [makeTextBlock(md)])];
    const matches = findMatches(messages, "python");
    expect(matches).toHaveLength(0);
  });

  it("finds matches in code block content", () => {
    const md = "Some text\n\n```python\nhello_world()\n```";
    const messages = [makeMessage("1", [makeTextBlock(md)])];
    const matches = findMatches(messages, "hello");
    expect(matches).toHaveLength(1);
  });

  it("finds matches across text and code blocks", () => {
    const md = "hello text\n\n```\nhello code\n```\n\nhello more";
    const messages = [makeMessage("1", [makeTextBlock(md)])];
    const matches = findMatches(messages, "hello");
    expect(matches).toHaveLength(3);
  });
});
