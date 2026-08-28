import { describe, expect, it } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";

import { segmentToolBlocks } from "../chipRowUtils.ts";

const DIFF_TOOL_NAMES = new Set(["Edit", "Write", "MultiEdit"]);

let idCounter = 0;
// Diff-tool fixtures carry a derivable file path (input.file_path for a
// tool_use, diff content with filePath for a tool_result) because real
// file-change tools always do. segmentToolBlocks only routes a diff tool to a
// chip when a path is derivable; path-less cases are covered explicitly below.
const makeToolUse = (name: string, id = `tu-${name}-${idCounter++}`): ToolUseBlock => ({
  type: "tool_use",
  objectType: "ToolUseBlock",
  id,
  name,
  input: DIFF_TOOL_NAMES.has(name) ? { file_path: `/repo/${name}.ts` } : {},
  invocationString: "",
});

const makeToolResult = (toolName: string, toolUseId = `tu-${toolName}`): ToolResultBlock => ({
  type: "tool_result",
  objectType: "ToolResultBlock",
  toolUseId,
  toolName,
  invocationString: "",
  content: DIFF_TOOL_NAMES.has(toolName)
    ? ({
        contentType: "diff",
        diff: "diff --git a/x b/x\n",
        filePath: `/repo/${toolName}.ts`,
      } as ToolResultBlock["content"])
    : ({ contentType: "generic", text: "ok" } as ToolResultBlock["content"]),
  isError: false,
});

// A diff-tool block with no derivable file path: a tool_use whose file_path
// hasn't streamed in yet, or a completed tool_result that fell back to generic
// content (e.g. a failed edit, or an edit to a file outside the workspace).
const makePathlessDiffToolUse = (name: string, id = `tu-${name}-${idCounter++}`): ToolUseBlock => ({
  type: "tool_use",
  objectType: "ToolUseBlock",
  id,
  name,
  input: {},
  invocationString: "",
});

const makeGenericDiffToolResult = (toolName: string, toolUseId = `tu-${toolName}`): ToolResultBlock => ({
  type: "tool_result",
  objectType: "ToolResultBlock",
  toolUseId,
  toolName,
  invocationString: "",
  content: { contentType: "generic", text: "File edited successfully." } as ToolResultBlock["content"],
  isError: false,
});

describe("segmentToolBlocks", () => {
  it("returns empty array for empty input", () => {
    expect(segmentToolBlocks([])).toEqual([]);
  });

  it("groups all diff tools into a single chip segment", () => {
    const blocks = [makeToolUse("Edit"), makeToolUse("Write"), makeToolUse("MultiEdit")];
    const segments = segmentToolBlocks(blocks);

    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("chip");
    expect(segments[0].blocks).toHaveLength(3);
  });

  it("groups all non-diff tools into a single tools segment", () => {
    const blocks = [makeToolUse("Read"), makeToolUse("Grep"), makeToolUse("Glob")];
    const segments = segmentToolBlocks(blocks);

    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("tools");
    expect(segments[0].blocks).toHaveLength(3);
  });

  it("alternates chip and tools segments for interleaved blocks", () => {
    const blocks = [makeToolUse("Edit"), makeToolUse("Read"), makeToolUse("Write")];
    const segments = segmentToolBlocks(blocks);

    expect(segments).toHaveLength(3);
    expect(segments[0].kind).toBe("chip");
    expect(segments[0].blocks).toHaveLength(1);
    expect(segments[1].kind).toBe("tools");
    expect(segments[1].blocks).toHaveLength(1);
    expect(segments[2].kind).toBe("chip");
    expect(segments[2].blocks).toHaveLength(1);
  });

  it("converts diff ToolResult blocks into chip shims", () => {
    const blocks = [makeToolResult("Edit", "tu-edit-1"), makeToolUse("Read")];
    const segments = segmentToolBlocks(blocks);

    // The Edit tool_result becomes a ToolUseBlock shim in a chip segment.
    expect(segments).toHaveLength(2);
    expect(segments[0].kind).toBe("chip");
    expect(segments[0].blocks).toHaveLength(1);
    expect(segments[0].blocks[0]).toMatchObject({ type: "tool_use", id: "tu-edit-1", name: "Edit" });
    expect(segments[1].kind).toBe("tools");
    expect(segments[1].blocks).toHaveLength(1);
  });

  it("merges diff tool_result shims with adjacent tool_use chips", () => {
    const editUse = makeToolUse("Edit", "tu-edit-1");
    const editResult = makeToolResult("Edit", "tu-edit-1");
    const writeUse = makeToolUse("Write", "tu-write-1");
    const writeResult = makeToolResult("Write", "tu-write-1");
    const blocks = [editUse, editResult, writeUse, writeResult];
    const segments = segmentToolBlocks(blocks);

    // All four blocks merge into one chip segment (results become shims).
    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("chip");
    expect(segments[0].blocks).toHaveLength(4);
  });

  it("creates chip shims for completed messages with only tool_result blocks", () => {
    // After completion, the backend replaces tool_use with tool_result.
    const blocks = [makeToolResult("Edit", "tu-1"), makeToolResult("Write", "tu-2")];
    const segments = segmentToolBlocks(blocks);

    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("chip");
    expect(segments[0].blocks).toHaveLength(2);
    expect(segments[0].blocks[0]).toMatchObject({ type: "tool_use", id: "tu-1", name: "Edit" });
    expect(segments[0].blocks[1]).toMatchObject({ type: "tool_use", id: "tu-2", name: "Write" });
  });

  it("merges consecutive diff tool_use blocks into one chip segment", () => {
    const blocks = [makeToolUse("Edit"), makeToolUse("Edit"), makeToolUse("MultiEdit")];
    const segments = segmentToolBlocks(blocks);

    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("chip");
    expect(segments[0].blocks).toHaveLength(3);
  });

  it("merges consecutive non-diff blocks into one tools segment", () => {
    const blocks = [makeToolUse("Read"), makeToolResult("Grep"), makeToolUse("Glob")];
    const segments = segmentToolBlocks(blocks);

    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("tools");
    expect(segments[0].blocks).toHaveLength(3);
  });

  describe("bash segmentation", () => {
    it("groups consecutive Bash tool_use blocks into a single tools segment", () => {
      const blocks = [makeToolUse("Bash", "b1"), makeToolUse("Bash", "b2")];
      const segments = segmentToolBlocks(blocks);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("tools");
      expect(segments[0].blocks).toHaveLength(2);
    });

    it("treats a Bash tool_result as part of a tools segment", () => {
      const blocks = [makeToolResult("Bash", "b1")];
      const segments = segmentToolBlocks(blocks);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("tools");
      expect(segments[0].blocks).toHaveLength(1);
    });

    it("groups bash with adjacent non-diff tools in one tools segment", () => {
      const blocks = [makeToolUse("Read"), makeToolUse("Bash")];
      const segments = segmentToolBlocks(blocks);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("tools");
      expect(segments[0].blocks).toHaveLength(2);
    });

    it("bash blocks flush pending chip batch", () => {
      const blocks = [makeToolUse("Edit"), makeToolUse("Bash")];
      const segments = segmentToolBlocks(blocks);

      expect(segments).toHaveLength(2);
      expect(segments[0].kind).toBe("chip");
      expect(segments[0].blocks).toHaveLength(1);
      expect(segments[1].kind).toBe("tools");
      expect(segments[1].blocks).toHaveLength(1);
    });

    it("interleaved bash, chip, and tools segments", () => {
      const blocks = [
        makeToolUse("Edit"),
        makeToolUse("Bash"),
        makeToolUse("Read"),
        makeToolUse("Bash"),
        makeToolUse("Write"),
      ];
      const segments = segmentToolBlocks(blocks);

      // Edit -> chip; Bash + Read + Bash -> tools; Write -> chip
      expect(segments).toHaveLength(3);
      expect(segments[0].kind).toBe("chip");
      expect(segments[0].blocks).toHaveLength(1);
      expect(segments[1].kind).toBe("tools");
      expect(segments[1].blocks).toHaveLength(3);
      expect(segments[2].kind).toBe("chip");
      expect(segments[2].blocks).toHaveLength(1);
    });

    it("merges consecutive Bash tool_use and tool_result into one tools segment", () => {
      const blocks = [makeToolUse("Bash", "b1"), makeToolResult("Bash", "b1")];
      const segments = segmentToolBlocks(blocks);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("tools");
      expect(segments[0].blocks).toHaveLength(2);
    });
  });

  describe("path-less diff tools fall back to tool pills", () => {
    // A chip requires a derivable file path; without one buildChipData would
    // silently drop the block, making the tool call vanish. These blocks must
    // fall back to a tool pill instead.
    it("routes a diff tool_result with generic content into a tools segment", () => {
      const segments = segmentToolBlocks([makeGenericDiffToolResult("Edit", "tu-1")]);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("tools");
      expect(segments[0].blocks).toHaveLength(1);
    });

    it("routes a diff tool_use without a file_path into a tools segment", () => {
      const segments = segmentToolBlocks([makePathlessDiffToolUse("Edit", "tu-1")]);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("tools");
      expect(segments[0].blocks).toHaveLength(1);
    });

    it("still routes a diff tool with a derivable path into a chip segment", () => {
      const segments = segmentToolBlocks([makeToolResult("Edit", "tu-1")]);

      expect(segments).toHaveLength(1);
      expect(segments[0].kind).toBe("chip");
    });
  });
});
