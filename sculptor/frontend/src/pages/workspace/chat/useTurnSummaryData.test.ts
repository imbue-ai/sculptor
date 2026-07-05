import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ChatMessage, DiffToolContent, ToolResultBlock, ToolUseBlock, TurnMetrics } from "~/api";
import { ChatMessageRole } from "~/api";
import type { SubagentTreeNode } from "~/pages/workspace/chat/utils/subagentTree";
import { DIFF_PAGINATION_FIX, DIFF_VALIDATORS_NEW } from "~/stories/custom/pages/workspace/chat/fixtures/diffData.ts";

import type { TurnFile } from "./useTurnSummaryData";
import { useTurnSummaryData } from "./useTurnSummaryData";

/** Create a ToolUseBlock (present during streaming, before replacement). */
const makeToolUse = (id: string, toolName: string, filePath: string): ToolUseBlock =>
  ({
    type: "tool_use",
    id,
    name: toolName,
    input: { file_path: filePath },
  }) as unknown as ToolUseBlock;

/** Create a ToolResultBlock with DiffToolContent (present after persistence). */
const makeDiffResult = (toolUseId: string, diff: string, filePath: string, isError = false): ToolResultBlock =>
  ({
    type: "tool_result",
    toolUseId,
    toolName: "Edit",
    invocationString: `Edit ${filePath}`,
    content: { contentType: "diff", diff, filePath } as DiffToolContent,
    isError,
  }) as unknown as ToolResultBlock;

/** Create a ToolResultBlock with GenericToolContent (non-file-changing tools). */
const makeGenericResult = (toolUseId: string, toolName: string, isError = false): ToolResultBlock =>
  ({
    type: "tool_result",
    toolUseId,
    toolName,
    invocationString: `${toolName} file`,
    content: { contentType: "generic", text: "ok" },
    isError,
  }) as unknown as ToolResultBlock;

const makeMessage = (content: ReadonlyArray<unknown>, overrides?: Partial<ChatMessage>): ChatMessage =>
  ({
    id: "msg-test",
    role: ChatMessageRole.ASSISTANT,
    approximateCreationTime: "2026-03-09T14:30:00.000Z",
    content,
    ...overrides,
  }) as unknown as ChatMessage;

const makeNode = (message: ChatMessage, childMessages: Array<ChatMessage> = []): SubagentTreeNode => ({
  message,
  children:
    childMessages.length > 0
      ? new Map([["child-tool", childMessages.map((m) => ({ message: m, children: new Map() }))]])
      : new Map(),
});

/** Create a SubagentTreeNode with explicit child nodes (for nested subagent trees). */
const makeNodeWithChildNodes = (message: ChatMessage, childNodes: Array<SubagentTreeNode> = []): SubagentTreeNode => ({
  message,
  children: childNodes.length > 0 ? new Map([["child-tool", childNodes]]) : new Map(),
});

const makeTurnMetrics = (overrides: Partial<TurnMetrics> = {}): TurnMetrics =>
  ({
    durationSeconds: 5.0,
    inputTokens: 100,
    outputTokens: 200,
    reasoningTokens: null,
    changedFiles: [],
    ...overrides,
  }) as TurnMetrics;

describe("useTurnSummaryData", () => {
  it("returns undefined when message has no tool uses or results", () => {
    const message = makeMessage([{ type: "text", text: "Hello" }]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("returns undefined when all tool results are errors", () => {
    const errorResult = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py", true);
    const message = makeMessage([errorResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("returns undefined for non-file-changing tools (Bash)", () => {
    const toolUse = { type: "tool_use", id: "tu-1", name: "Bash", input: { command: "echo hi" } };
    const genericResult = makeGenericResult("tu-1", "Bash");
    const message = makeMessage([toolUse, genericResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("extracts file path from ToolUseBlock.input during streaming", () => {
    const toolUse = makeToolUse("tu-1", "Edit", "utils/pagination.py");
    const genericResult = makeGenericResult("tu-1", "Edit");
    const message = makeMessage([toolUse, genericResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
    expect(files[0].status).toBe("modified");
  });

  it("extracts file path from Write ToolUseBlock", () => {
    const toolUse = makeToolUse("tu-1", "Write", "utils/validators.py");
    const genericResult = makeGenericResult("tu-1", "Write");
    const message = makeMessage([toolUse, genericResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/validators.py");
  });

  it("skips ToolUseBlock whose result is an error", () => {
    const toolUse = makeToolUse("tu-1", "Edit", "utils/pagination.py");
    const errorResult = makeGenericResult("tu-1", "Edit", true);
    const message = makeMessage([toolUse, errorResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("extracts file path from DiffToolContent after persistence", () => {
    const diffResult = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const message = makeMessage([diffResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
    expect(files[0].status).toBe("modified");
  });

  it("extracts file path from new-file DiffToolContent", () => {
    const diffResult = makeDiffResult("tu-1", DIFF_VALIDATORS_NEW, "utils/validators.py");
    const message = makeMessage([diffResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/validators.py");
    expect(files[0].status).toBe("modified");
  });

  it("skips DiffToolContent when result is an error", () => {
    const errorResult = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py", true);
    const message = makeMessage([errorResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("deduplicates when both ToolUseBlock and DiffToolContent provide the same path", () => {
    const toolUse = makeToolUse("tu-1", "Edit", "utils/pagination.py");
    const diffResult = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const message = makeMessage([toolUse, diffResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
  });

  it("deduplicates multiple edits to the same file", () => {
    const result1 = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const result2 = makeDiffResult("tu-2", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const message = makeMessage([result1, result2]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
  });

  it("returns multiple TurnFiles for different files in insertion order", () => {
    const result1 = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const result2 = makeDiffResult("tu-2", DIFF_VALIDATORS_NEW, "utils/validators.py");
    const message = makeMessage([result1, result2]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(2);
    expect(files[0].path).toBe("utils/pagination.py");
    expect(files[1].path).toBe("utils/validators.py");
  });

  it("includes file changes from subagent child messages", () => {
    const parentMessage = makeMessage([{ type: "text", text: "Starting" }], { id: "parent" });
    const childMessage = makeMessage([makeDiffResult("tu-child", DIFF_VALIDATORS_NEW, "utils/validators.py")], {
      id: "child",
    });
    const node = makeNode(parentMessage, [childMessage]);

    const { result } = renderHook(() => useTurnSummaryData(node));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/validators.py");
    expect(files[0].status).toBe("modified");
  });

  it("combines parent and subagent file changes", () => {
    const parentDiff = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const parentMessage = makeMessage([parentDiff], { id: "parent" });
    const childMessage = makeMessage([makeDiffResult("tu-child", DIFF_VALIDATORS_NEW, "utils/validators.py")], {
      id: "child",
    });
    const node = makeNode(parentMessage, [childMessage]);

    const { result } = renderHook(() => useTurnSummaryData(node));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(2);
    expect(files[0].path).toBe("utils/pagination.py");
    expect(files[1].path).toBe("utils/validators.py");
  });

  it("deduplicates same file across parent and subagent messages", () => {
    const parentDiff = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const parentMessage = makeMessage([parentDiff], { id: "parent" });
    const childMessage = makeMessage([makeDiffResult("tu-child", DIFF_PAGINATION_FIX, "utils/pagination.py")], {
      id: "child",
    });
    const node = makeNode(parentMessage, [childMessage]);

    const { result } = renderHook(() => useTurnSummaryData(node));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
  });

  it("extracts file path from MultiEdit ToolUseBlock", () => {
    const toolUse = makeToolUse("tu-1", "MultiEdit", "utils/pagination.py");
    const genericResult = makeGenericResult("tu-1", "MultiEdit");
    const message = makeMessage([toolUse, genericResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
  });

  it("skips ToolUseBlock with missing file_path input", () => {
    const toolUse = {
      type: "tool_use",
      id: "tu-1",
      name: "Edit",
      input: {},
    } as unknown as ToolUseBlock;
    const genericResult = makeGenericResult("tu-1", "Edit");
    const message = makeMessage([toolUse, genericResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("skips ToolUseBlock with non-string file_path input", () => {
    const toolUse = {
      type: "tool_use",
      id: "tu-1",
      name: "Edit",
      input: { file_path: 42 },
    } as unknown as ToolUseBlock;
    const genericResult = makeGenericResult("tu-1", "Edit");
    const message = makeMessage([toolUse, genericResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("ignores Read/Grep/Glob tools (not file-changing)", () => {
    const readTool = makeToolUse("tu-1", "Read", "utils/pagination.py");
    const grepTool = makeToolUse("tu-2", "Grep", "utils/validators.py");
    const globTool = makeToolUse("tu-3", "Glob", "utils/helpers.py");
    const message = makeMessage([
      readTool,
      makeGenericResult("tu-1", "Read"),
      grepTool,
      makeGenericResult("tu-2", "Grep"),
      globTool,
      makeGenericResult("tu-3", "Glob"),
    ]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("handles message with only text blocks (no tools)", () => {
    const message = makeMessage([
      { type: "text", text: "First paragraph." },
      { type: "text", text: "Second paragraph." },
    ]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));
    expect(result.current).toBeUndefined();
  });

  it("handles mixed successful and errored tool uses correctly", () => {
    const successToolUse = makeToolUse("tu-1", "Edit", "utils/pagination.py");
    const errorToolUse = makeToolUse("tu-2", "Edit", "utils/validators.py");
    const successResult = makeGenericResult("tu-1", "Edit", false);
    const errorResult = makeGenericResult("tu-2", "Edit", true);
    const message = makeMessage([successToolUse, errorToolUse, successResult, errorResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
  });

  it("uses turnMetrics.changedFiles as authoritative source when available", () => {
    const message = makeMessage([{ type: "text", text: "Done" }], {
      turnMetrics: makeTurnMetrics({ changedFiles: ["config.yaml", "README.md"] }),
    });
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(2);
    expect(files[0].path).toBe("config.yaml");
    expect(files[1].path).toBe("README.md");
  });

  it("includes Bash-created files via turnMetrics.changedFiles", () => {
    // Bash tool use does not produce DiffToolContent, but backend detects the change
    const toolUse = { type: "tool_use", id: "tu-1", name: "Bash", input: { command: "echo hi > new.txt" } };
    const genericResult = makeGenericResult("tu-1", "Bash");
    const message = makeMessage([toolUse, genericResult], {
      turnMetrics: makeTurnMetrics({ changedFiles: ["new.txt"] }),
    });
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("new.txt");
  });

  it("falls back to streaming sources when turnMetrics.changedFiles is empty", () => {
    const toolUse = makeToolUse("tu-1", "Edit", "utils/pagination.py");
    const genericResult = makeGenericResult("tu-1", "Edit");
    const message = makeMessage([toolUse, genericResult], {
      turnMetrics: makeTurnMetrics({ changedFiles: [] }),
    });
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
  });

  it("falls back to streaming sources when turnMetrics is absent", () => {
    const diffResult = makeDiffResult("tu-1", DIFF_PAGINATION_FIX, "utils/pagination.py");
    const message = makeMessage([diffResult]);
    const { result } = renderHook(() => useTurnSummaryData(makeNode(message)));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(1);
    expect(files[0].path).toBe("utils/pagination.py");
  });

  it("includes file changes from nested sub-subagent messages", () => {
    const parentMessage = makeMessage([{ type: "text", text: "Starting" }], { id: "parent" });
    const childMessage = makeMessage([makeDiffResult("tu-child", DIFF_PAGINATION_FIX, "utils/pagination.py")], {
      id: "child",
    });
    const grandchildMessage = makeMessage([makeDiffResult("tu-gc", DIFF_VALIDATORS_NEW, "utils/validators.py")], {
      id: "grandchild",
    });

    // Build: parent -> child -> grandchild
    const grandchildNode = makeNodeWithChildNodes(grandchildMessage);
    const childNode = makeNodeWithChildNodes(childMessage, [grandchildNode]);
    const parentNode = makeNodeWithChildNodes(parentMessage, [childNode]);

    const { result } = renderHook(() => useTurnSummaryData(parentNode));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(2);
    expect(files[0].path).toBe("utils/pagination.py");
    expect(files[1].path).toBe("utils/validators.py");
  });

  it("uses backend changedFiles from subagent children when available", () => {
    const parentMessage = makeMessage([{ type: "text", text: "Starting" }], {
      id: "parent",
      turnMetrics: makeTurnMetrics({ changedFiles: ["parent.py"] }),
    });
    const childMessage = makeMessage([{ type: "text", text: "Done" }], {
      id: "child",
      turnMetrics: makeTurnMetrics({ changedFiles: ["child.py"] }),
    });
    const node = makeNode(parentMessage, [childMessage]);

    const { result } = renderHook(() => useTurnSummaryData(node));

    expect(result.current).toBeDefined();
    const files = result.current as ReadonlyArray<TurnFile>;
    expect(files).toHaveLength(2);
    expect(files[0].path).toBe("parent.py");
    expect(files[1].path).toBe("child.py");
  });
});
