import { describe, expect, it } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";

import { buildPillData, makeRelative } from "../toolPillUtils.ts";

// ---------------------------------------------------------------------------
// Factories
// ---------------------------------------------------------------------------

const makeToolUseBlock = (overrides: Partial<ToolUseBlock> & { id: string; name: string }): ToolUseBlock => ({
  type: "tool_use",
  objectType: "ToolUseBlock",
  invocationString: "",
  ...overrides,
});

const makeToolResultBlock = (toolUseId: string, overrides: Partial<ToolResultBlock> = {}): ToolResultBlock => ({
  type: "tool_result",
  objectType: "ToolResultBlock",
  toolUseId,
  toolName: "Bash",
  invocationString: "",
  content: { contentType: "generic", text: "" },
  isError: false,
  ...overrides,
});

// ---------------------------------------------------------------------------
// makeRelative — used by AlphaToolPopover to display project-relative paths.
// ---------------------------------------------------------------------------

describe("makeRelative", () => {
  it("strips the workspace prefix from absolute paths under the workspace", () => {
    expect(makeRelative("/workspace/code/src/index.ts", "/workspace/code")).toEqual({
      display: "src/index.ts",
      isOutsideWorkspace: false,
    });
  });

  it("handles a workspace path with a trailing slash", () => {
    expect(makeRelative("/workspace/code/src/index.ts", "/workspace/code/")).toEqual({
      display: "src/index.ts",
      isOutsideWorkspace: false,
    });
  });

  it("flags absolute paths outside the workspace as such", () => {
    expect(makeRelative("/other/place/file.ts", "/workspace/code")).toEqual({
      display: "/other/place/file.ts",
      isOutsideWorkspace: true,
    });
  });

  it("flags absolute paths as outside when no workspace is configured", () => {
    expect(makeRelative("/abs/file.ts", null)).toEqual({
      display: "/abs/file.ts",
      isOutsideWorkspace: true,
    });
  });

  it("returns relative paths verbatim", () => {
    expect(makeRelative("src/foo.ts", "/workspace/code")).toEqual({
      display: "src/foo.ts",
      isOutsideWorkspace: false,
    });
  });

  it("returns an empty display when filePath equals the workspace root", () => {
    expect(makeRelative("/workspace/code", "/workspace/code")).toEqual({
      display: "",
      isOutsideWorkspace: false,
    });
  });
});

// ---------------------------------------------------------------------------
// buildPillData – one pill per tool call
// ---------------------------------------------------------------------------

describe("buildPillData", () => {
  it("produces one pill per tool block, preserving order and labels", () => {
    const blocks = [
      makeToolUseBlock({ id: "1", name: "Bash", input: { command: "ls" } }),
      makeToolUseBlock({ id: "2", name: "Read", input: { file_path: "foo.ts" } }),
    ];
    const resultMap = new Map([
      ["1", makeToolResultBlock("1")],
      ["2", makeToolResultBlock("2")],
    ]);

    const pills = buildPillData(blocks, resultMap, null);
    expect(pills).toHaveLength(2);
    expect(pills[0].label).toBe("Bash");
    expect(pills[1].label).toBe("Read");
    expect(pills.map((p) => p.id)).toEqual(["1", "2"]);
  });

  it("emits one pill per block even when all share the same tool type", () => {
    const blocks = [
      makeToolUseBlock({ id: "1", name: "Bash", input: { command: "ls" } }),
      makeToolUseBlock({ id: "2", name: "Bash", input: { command: "pwd" } }),
      makeToolUseBlock({ id: "3", name: "Bash", input: { command: "cat" } }),
    ];
    const resultMap = new Map([
      ["1", makeToolResultBlock("1")],
      ["2", makeToolResultBlock("2")],
      ["3", makeToolResultBlock("3")],
    ]);

    const pills = buildPillData(blocks, resultMap, null);
    expect(pills).toHaveLength(3);
    expect(pills.every((p) => p.label === "Bash")).toBe(true);
  });

  it("attaches the matching result to each pill", () => {
    const blocks = [makeToolUseBlock({ id: "1", name: "Bash" })];
    const result = makeToolResultBlock("1");
    const pills = buildPillData(blocks, new Map([["1", result]]), null);
    expect(pills[0].results).toEqual([result]);
    expect(pills[0].blocks).toEqual([blocks[0]]);
  });

  it("marks completed pills as completed and pending pills as initializing during execution", () => {
    const blocks = [
      makeToolUseBlock({ id: "1", name: "Bash", input: { command: "ls" } }),
      makeToolUseBlock({ id: "2", name: "Read", input: { file_path: "foo.ts" } }),
      makeToolUseBlock({ id: "3", name: "Edit", input: { file_path: "bar.ts" } }),
    ];
    // Only first two have results; third is still running.
    const resultMap = new Map([
      ["1", makeToolResultBlock("1")],
      ["2", makeToolResultBlock("2")],
    ]);

    const pills = buildPillData(blocks, resultMap, "msg-1");
    expect(pills[0].state).toBe("completed");
    expect(pills[1].state).toBe("completed");
    expect(pills[2].state).toBe("initializing");
  });

  it("sets initializing state when no result and the message is in progress", () => {
    const blocks = [makeToolUseBlock({ id: "1", name: "Bash" })];
    const pills = buildPillData(blocks, new Map(), "msg-1");
    expect(pills[0].state).toBe("initializing");
  });

  it("sets completed state when no result but the message is no longer in progress", () => {
    const blocks = [makeToolUseBlock({ id: "1", name: "Bash" })];
    const pills = buildPillData(blocks, new Map(), null);
    expect(pills[0].state).toBe("completed");
  });

  it("sets error state when the result has isError", () => {
    const blocks = [makeToolUseBlock({ id: "1", name: "Bash" })];
    const resultMap = new Map([["1", makeToolResultBlock("1", { isError: true })]]);
    const pills = buildPillData(blocks, resultMap, null);
    expect(pills[0].state).toBe("error");
  });

  it("returns an empty array for empty input", () => {
    expect(buildPillData([], new Map(), null)).toHaveLength(0);
  });

  it("dedupes a tool_use and its matching tool_result in the same blocks list", () => {
    // During the streaming transition into Sculptor's result-replaced form,
    // a single message snapshot can briefly carry both the tool_use and its
    // tool_result for the same call. The pill row should render once per
    // call, not twice.
    const toolUse = makeToolUseBlock({ id: "1", name: "Bash", input: { command: "ls" } });
    const toolResult = makeToolResultBlock("1", { toolName: "Bash" });
    const pills = buildPillData([toolUse, toolResult], new Map([["1", toolResult]]), null);
    expect(pills).toHaveLength(1);
    expect(pills[0].id).toBe("1");
    expect(pills[0].blocks).toEqual([toolUse]);
    expect(pills[0].results).toEqual([toolResult]);
  });

  it("dedupes across many parallel calls when both shapes are present", () => {
    const toolUses = Array.from({ length: 9 }, (_, i) =>
      makeToolUseBlock({ id: `t${i}`, name: "Bash", input: { command: `cmd-${i}` } }),
    );
    const toolResults = toolUses.map((u) => makeToolResultBlock(u.id, { toolName: "Bash" }));
    const pills = buildPillData([...toolUses, ...toolResults], new Map(toolResults.map((r) => [r.toolUseId, r])), null);
    expect(pills).toHaveLength(9);
    expect(pills.map((p) => p.id)).toEqual(toolUses.map((u) => u.id));
  });
});

// ---------------------------------------------------------------------------
// buildPillData – result-only blocks (no tool_use)
// ---------------------------------------------------------------------------

describe("buildPillData – result-only blocks", () => {
  it("emits one pill per result-only block", () => {
    const blocks: Array<ToolResultBlock> = [
      makeToolResultBlock("1", { toolName: "Bash", invocationString: "ls -la" }),
      makeToolResultBlock("2", { toolName: "Read", invocationString: "foo.ts" }),
    ];

    const pills = buildPillData(blocks, new Map(), null);
    expect(pills).toHaveLength(2);
    expect(pills[0].label).toBe("Bash");
    expect(pills[1].label).toBe("Read");
    expect(pills.map((p) => p.id)).toEqual(["1", "2"]);
  });

  it("uses toolUseId as the pill id and surfaces the result on the pill", () => {
    const result = makeToolResultBlock("1", { toolName: "Bash" });
    const pills = buildPillData([result], new Map(), null);
    expect(pills[0].id).toBe("1");
    expect(pills[0].blocks).toEqual([]);
    expect(pills[0].results).toEqual([result]);
  });

  it("sets error state when the result has isError", () => {
    const blocks: Array<ToolResultBlock> = [makeToolResultBlock("1", { toolName: "Bash", isError: true })];
    const pills = buildPillData(blocks, new Map(), null);
    expect(pills[0].state).toBe("error");
  });

  it('defaults toolName to "tool" when missing', () => {
    const block: ToolResultBlock = {
      type: "tool_result",
      objectType: "ToolResultBlock",
      toolUseId: "1",
      toolName: undefined as unknown as string,
      invocationString: "",
      content: { contentType: "generic", text: "" },
      isError: false,
    };

    const pills = buildPillData([block], new Map(), null);
    expect(pills[0].label).toBe("tool");
  });
});
