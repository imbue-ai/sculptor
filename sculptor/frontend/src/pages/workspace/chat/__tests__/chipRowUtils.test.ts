import { describe, expect, it } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";

import { buildChipData, disambiguateFileNames, getFilePathFromToolBlock, segmentToolBlocks } from "../chipRowUtils.ts";

const makeToolUseBlock = (overrides: Partial<ToolUseBlock> & { id: string; name: string }): ToolUseBlock => ({
  type: "tool_use",
  objectType: "ToolUseBlock",
  invocationString: "",
  ...overrides,
});

const makeDiffResult = (toolUseId: string, filePath: string, diff: string, isError = false): ToolResultBlock => ({
  type: "tool_result",
  objectType: "ToolResultBlock",
  toolUseId,
  toolName: "Edit",
  invocationString: filePath,
  content: { contentType: "diff", diff, filePath },
  isError,
});

const makeGenericResult = (toolUseId: string, text: string, isError = false): ToolResultBlock => ({
  type: "tool_result",
  objectType: "ToolResultBlock",
  toolUseId,
  toolName: "Edit",
  invocationString: "",
  content: { contentType: "generic", text },
  isError,
});

// Mirror of resultToToolUseShim in chipRowUtils — the shim shape that
// segmentToolBlocks pushes for a diff-tool tool_result during the
// streaming transition. Empty input on purpose: shims have no input.
const makeShim = (id: string, filePath: string): ToolUseBlock => ({
  type: "tool_use",
  objectType: "ToolUseBlock",
  id,
  name: "Edit",
  input: {},
  invocationString: filePath,
});

const SIMPLE_DIFF = `diff --git a/foo.ts b/foo.ts
index 1234..5678 100644
--- a/foo.ts
+++ b/foo.ts
@@ -1,3 +1,4 @@
 line1
+added
 line2
 line3
`;

describe("getFilePathFromToolBlock", () => {
  it("returns filePath from DiffToolContent result when available", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "old/path.ts" } });
    const result = makeDiffResult("1", "new/path.ts", SIMPLE_DIFF);
    expect(getFilePathFromToolBlock(block, result)).toBe("new/path.ts");
  });

  it("falls back to block.input.file_path when no result", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/index.ts" } });
    expect(getFilePathFromToolBlock(block)).toBe("src/index.ts");
  });

  it("falls back to block.input.file_path when result is generic (not diff)", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/index.ts" } });
    const result = makeGenericResult("1", "some output");
    expect(getFilePathFromToolBlock(block, result)).toBe("src/index.ts");
  });

  it("returns null when input is undefined", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit" });
    expect(getFilePathFromToolBlock(block)).toBeNull();
  });

  it("returns null when file_path is not a string", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: 123 } });
    expect(getFilePathFromToolBlock(block)).toBeNull();
  });
});

describe("disambiguateFileNames", () => {
  it("returns just the basename for unique files", () => {
    const result = disambiguateFileNames(["src/foo.ts", "src/bar.ts"]);
    expect(result.get("src/foo.ts")).toBe("foo.ts");
    expect(result.get("src/bar.ts")).toBe("bar.ts");
  });

  it("returns just the basename for deeply nested unique files", () => {
    const result = disambiguateFileNames(["a/b/c/foo.ts"]);
    expect(result.get("a/b/c/foo.ts")).toBe("foo.ts");
  });

  it("adds minimal prefix for duplicate basenames", () => {
    const result = disambiguateFileNames(["src/utils/index.ts", "tests/utils/index.ts"]);
    expect(result.get("src/utils/index.ts")).toBe("src/.../index.ts");
    expect(result.get("tests/utils/index.ts")).toBe("tests/.../index.ts");
  });

  it("uses immediate parent when depth-2 disambiguation suffices", () => {
    const result = disambiguateFileNames(["src/foo.ts", "lib/foo.ts"]);
    expect(result.get("src/foo.ts")).toBe("src/.../foo.ts");
    expect(result.get("lib/foo.ts")).toBe("lib/.../foo.ts");
  });

  it("handles single path", () => {
    const result = disambiguateFileNames(["src/foo.ts"]);
    expect(result.get("src/foo.ts")).toBe("foo.ts");
  });

  it("returns empty map for empty input", () => {
    const result = disambiguateFileNames([]);
    expect(result.size).toBe(0);
  });

  it("handles three files with same basename at different depths", () => {
    const result = disambiguateFileNames([
      "a/shared/utils/index.ts",
      "b/shared/utils/index.ts",
      "c/other/utils/index.ts",
    ]);
    // a/shared and b/shared share the "shared" parent too, so must go deeper
    expect(result.get("a/shared/utils/index.ts")).toBe("a/.../index.ts");
    expect(result.get("b/shared/utils/index.ts")).toBe("b/.../index.ts");
    // c is unique at the "other" level
    expect(result.get("c/other/utils/index.ts")).toBe("other/.../index.ts");
  });

  it("renders bare basename for duplicate identical paths", () => {
    // Two mentions of the same file aren't a collision — they're the same
    // thing shown twice. Render the basename, not the full path.
    const result = disambiguateFileNames(["src/utils/helper.ts", "src/utils/helper.ts"]);
    expect(result.get("src/utils/helper.ts")).toBe("helper.ts");
  });

  it("disambiguates deeply nested files with same structure", () => {
    const result = disambiguateFileNames(["a/b/c/d/index.ts", "x/b/c/d/index.ts"]);
    expect(result.get("a/b/c/d/index.ts")).toBe("a/.../index.ts");
    expect(result.get("x/b/c/d/index.ts")).toBe("x/.../index.ts");
  });

  it("returns just the filename for a file with no directory", () => {
    const result = disambiguateFileNames(["file.ts"]);
    expect(result.get("file.ts")).toBe("file.ts");
  });

  it("handles files with only basename (no directory) that share the same name", () => {
    // When paths have no directory segments to disambiguate, fall back to full path
    const result = disambiguateFileNames(["index.ts", "index.ts"]);
    expect(result.get("index.ts")).toBe("index.ts");
  });

  it("handles paths with special characters", () => {
    const result = disambiguateFileNames(["src/[components]/Button.tsx", "src/utils/Button.tsx"]);
    expect(result.get("src/[components]/Button.tsx")).toBe("[components]/.../Button.tsx");
    expect(result.get("src/utils/Button.tsx")).toBe("utils/.../Button.tsx");
  });
});

describe("buildChipData", () => {
  it("returns one completed chip for a single completed block", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([["1", result]]);

    const chips = buildChipData([block], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("completed");
    expect(chips[0].filePath).toBe("src/foo.ts");
    expect(chips[0].displayName).toBe("foo.ts");
    expect(chips[0].stats).toEqual({ added: 1, removed: 0 });
  });

  it("merges two completed blocks targeting the same file", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result1 = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const result2 = makeDiffResult("2", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
    ]);

    const chips = buildChipData([block1, block2], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].blocks).toHaveLength(2);
    expect(chips[0].stats).toEqual({ added: 2, removed: 0 });
  });

  it("splits mixed-state blocks targeting the same file", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result1 = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const result2 = makeGenericResult("2", "Edit failed: old_string not found", true);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
    ]);

    const chips = buildChipData([block1, block2], resultMap, null);
    expect(chips).toHaveLength(2);
    expect(chips[0].state).toBe("completed");
    expect(chips[1].state).toBe("error");
    expect(chips[1].errorDetail).toBe("Edit failed: old_string not found");
    expect(chips[1].errorContentType).toBe("text");
  });

  it("sets errorContentType to 'diff' for DiffToolContent errors", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result: ToolResultBlock = {
      type: "tool_result",
      toolUseId: "1",
      toolName: "Edit",
      invocationString: "Edit(…)",
      content: { contentType: "diff", diff: SIMPLE_DIFF, filePath: "src/foo.ts" },
      isError: true,
    };
    const resultMap = new Map([["1", result]]);

    const chips = buildChipData([block], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("error");
    expect(chips[0].errorDetail).toBe(SIMPLE_DIFF);
    expect(chips[0].errorContentType).toBe("diff");
  });

  it("returns executing chip when block has no result and message is in progress", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const resultMap = new Map<string, ToolResultBlock>();

    const chips = buildChipData([block], resultMap, "msg-1");
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("executing");
    expect(chips[0].stats).toBeNull();
  });

  it("optimistic merge: two blocks same file, one executing one completed — shows partial stats", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result1 = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([["1", result1]]);

    const chips = buildChipData([block1, block2], resultMap, "msg-1");
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("executing");
    // Partial stats from the completed block are shown during execution
    expect(chips[0].stats).toEqual({ added: 1, removed: 0 });
  });

  it("skips blocks with null filePath", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit" }); // no input
    const resultMap = new Map<string, ToolResultBlock>();

    const chips = buildChipData([block], resultMap, null);
    expect(chips).toHaveLength(0);
  });

  it("sets isNewFile true for Write tool", () => {
    const block = makeToolUseBlock({ id: "1", name: "Write", input: { file_path: "src/new.ts" } });
    const result = makeDiffResult("1", "src/new.ts", SIMPLE_DIFF);
    const resultMap = new Map([["1", result]]);

    const chips = buildChipData([block], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].isNewFile).toBe(true);
  });

  it("sets isNewFile false for Edit tool", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([["1", result]]);

    const chips = buildChipData([block], resultMap, null);
    expect(chips[0].isNewFile).toBe(false);
  });

  it("disambiguates files with the same basename", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/utils/index.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "tests/utils/index.ts" } });
    const result1 = makeDiffResult("1", "src/utils/index.ts", SIMPLE_DIFF);
    const result2 = makeDiffResult("2", "tests/utils/index.ts", SIMPLE_DIFF);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
    ]);

    const chips = buildChipData([block1, block2], resultMap, null);
    expect(chips).toHaveLength(2);
    expect(chips[0].displayName).toBe("src/.../index.ts");
    expect(chips[1].displayName).toBe("tests/.../index.ts");
  });

  it("handles multiple files with different states in one call", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/a.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/b.ts" } });
    const block3 = makeToolUseBlock({ id: "3", name: "Edit", input: { file_path: "src/c.ts" } });
    const result1 = makeDiffResult("1", "src/a.ts", SIMPLE_DIFF);
    const result2 = makeGenericResult("2", "something went wrong", true);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
    ]);

    const chips = buildChipData([block1, block2, block3], resultMap, "msg-1");
    expect(chips).toHaveLength(3);
    expect(chips[0].state).toBe("completed");
    expect(chips[1].state).toBe("error");
    expect(chips[2].state).toBe("executing");
  });

  it("merges three completed blocks on the same file with aggregated stats", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block3 = makeToolUseBlock({ id: "3", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result1 = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const result2 = makeDiffResult("2", "src/foo.ts", SIMPLE_DIFF);
    const result3 = makeDiffResult("3", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
      ["3", result3],
    ]);

    const chips = buildChipData([block1, block2, block3], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].blocks).toHaveLength(3);
    expect(chips[0].stats).toEqual({ added: 3, removed: 0 });
  });

  it("returns null stats for a completed block with GenericToolContent result", () => {
    const block = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result = makeGenericResult("1", "done");
    const resultMap = new Map([["1", result]]);

    const chips = buildChipData([block], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("completed");
    // Stats are computed but no diff content contributes, so added/removed are both 0
    expect(chips[0].stats).toEqual({ added: 0, removed: 0 });
  });

  it("aggregates stats for two Write blocks to the same file", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Write", input: { file_path: "src/new.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Write", input: { file_path: "src/new.ts" } });
    const result1 = makeDiffResult("1", "src/new.ts", SIMPLE_DIFF);
    const result2 = makeDiffResult("2", "src/new.ts", SIMPLE_DIFF);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
    ]);

    const chips = buildChipData([block1, block2], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].isNewFile).toBe(true);
    expect(chips[0].stats).toEqual({ added: 2, removed: 0 });
  });

  it("sets isNewFile false when mixing Write and Edit on the same file", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Write", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result1 = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const result2 = makeDiffResult("2", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([
      ["1", result1],
      ["2", result2],
    ]);

    const chips = buildChipData([block1, block2], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].isNewFile).toBe(false);
  });

  it("returns empty chips for empty blocks array", () => {
    const resultMap = new Map<string, ToolResultBlock>();
    const chips = buildChipData([], resultMap, null);
    expect(chips).toHaveLength(0);
  });

  it("skips multiple blocks with null file paths", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit" });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit" });
    const block3 = makeToolUseBlock({ id: "3", name: "Edit", input: { file_path: 42 } });
    const resultMap = new Map<string, ToolResultBlock>();

    const chips = buildChipData([block1, block2, block3], resultMap, null);
    expect(chips).toHaveLength(0);
  });

  it("executing chip with no completed siblings shows null stats", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const resultMap = new Map<string, ToolResultBlock>();

    const chips = buildChipData([block1, block2], resultMap, "msg-1");
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("executing");
    expect(chips[0].stats).toBeNull();
  });

  it("executing chip with completed GenericToolContent shows null stats (no diff data)", () => {
    const block1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const block2 = makeToolUseBlock({ id: "2", name: "Edit", input: { file_path: "src/foo.ts" } });
    const result1 = makeGenericResult("1", "done");
    const resultMap = new Map([["1", result1]]);

    const chips = buildChipData([block1, block2], resultMap, "msg-1");
    expect(chips).toHaveLength(1);
    expect(chips[0].state).toBe("executing");
    // GenericToolContent has no diff, so stats stay null
    expect(chips[0].stats).toBeNull();
  });

  it("dedupes a tool_use and its matching tool_result-shim for the same Edit (SCU-470)", () => {
    // During the streaming transition into Sculptor's result-replaced form,
    // a single message snapshot can briefly carry both the tool_use and its
    // tool_result for the same call. segmentToolBlocks converts the
    // tool_result side into a ToolUseBlock shim with the SAME id, so the
    // chipBlocks array briefly contains both shapes.
    //
    // Without deduplication, buildChipData would walk both entries, fetch
    // the same result twice, and double the line counts — the user sees
    // "+1" briefly flicker to "+2" before settling back to "+1".
    const realBlock = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    const shimBlock = makeShim("1", "src/foo.ts");
    const result = makeDiffResult("1", "src/foo.ts", SIMPLE_DIFF);
    const resultMap = new Map([["1", result]]);

    const chips = buildChipData([realBlock, shimBlock], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].blocks).toHaveLength(1);
    // Stats must reflect the underlying diff exactly once — not doubled.
    expect(chips[0].stats).toEqual({ added: 1, removed: 0 });
    // The kept block is the real tool_use with its actual input, not the
    // shim — downstream code that reads block.input.file_path keeps working.
    expect(chips[0].blocks[0]).toBe(realBlock);
  });

  it("dedupes across many parallel Edits when both shapes are present (SCU-470)", () => {
    // The 3-parallel-Edit shape that triggers the user-reported "1 to 3
    // back to 1" flicker: the same file is edited three times in parallel,
    // and a transitional snapshot carries both the real tool_use and the
    // shimmed tool_result for each call. Without dedup, the merged chip's
    // line counts triple (3 real + 3 shim contributions for 3 calls).
    const ids = ["a", "b", "c"];
    const realBlocks = ids.map((id) => makeToolUseBlock({ id, name: "Edit", input: { file_path: "src/foo.ts" } }));
    const shimBlocks = ids.map((id) => makeShim(id, "src/foo.ts"));
    const results = ids.map((id) => makeDiffResult(id, "src/foo.ts", SIMPLE_DIFF));
    const resultMap = new Map(results.map((r) => [r.toolUseId, r]));

    const chips = buildChipData([...realBlocks, ...shimBlocks], resultMap, null);
    expect(chips).toHaveLength(1);
    expect(chips[0].blocks).toHaveLength(3);
    // Three Edits with +1 each — total +3, not +6.
    expect(chips[0].stats).toEqual({ added: 3, removed: 0 });
  });

  it("does not let a non-usable block shadow a later usable block with the same id (SCU-470)", () => {
    // Defensive ordering check: a block whose filePath can't yet be derived
    // (here: a shim with empty input and no result yet in the toolResultMap)
    // must not mark its id as seen, because a later block with the same id
    // that is usable (here: the real tool_use with a streamed-in
    // input.file_path) would otherwise be silently dropped.
    const partialShim = makeShim("1", "src/foo.ts"); // empty input
    const real = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "src/foo.ts" } });
    // Empty resultMap: the shim falls through to block.input (empty) and
    // returns null; the real still resolves via its own input.file_path.
    const resultMap = new Map<string, ToolResultBlock>();

    const chips = buildChipData([partialShim, real], resultMap, "msg-1");
    expect(chips).toHaveLength(1);
    expect(chips[0].blocks).toHaveLength(1);
    expect(chips[0].blocks[0]).toBe(real);
  });
});

describe("segmentToolBlocks", () => {
  it("places a single non-diff tool_result into a tools segment", () => {
    const block: ToolResultBlock = {
      type: "tool_result",
      objectType: "ToolResultBlock",
      toolUseId: "1",
      toolName: "Read",
      invocationString: "Read(…)",
      content: { contentType: "generic", text: "file contents" },
      isError: false,
    };

    const segments = segmentToolBlocks([block]);
    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("tools");
    expect(segments[0].blocks).toHaveLength(1);
  });

  it("groups bash tool_uses into a single tools segment with other non-diff tools", () => {
    const bash1 = makeToolUseBlock({ id: "1", name: "Bash", input: { command: "ls" } });
    const bash2 = makeToolUseBlock({ id: "2", name: "Bash", input: { command: "pwd" } });

    const segments = segmentToolBlocks([bash1, bash2]);
    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("tools");
    expect(segments[0].blocks).toHaveLength(2);
  });

  it("segments a long mixed sequence into chip and tools segments", () => {
    // Sequence: chip, tools (read+bash), chip (write), tools (bash+grep)
    const editBlock1 = makeToolUseBlock({ id: "1", name: "Edit", input: { file_path: "a.ts" } });
    const readBlock: ToolResultBlock = {
      type: "tool_result",
      objectType: "ToolResultBlock",
      toolUseId: "2",
      toolName: "Read",
      invocationString: "Read(…)",
      content: { contentType: "generic", text: "contents" },
      isError: false,
    };
    const bashBlock1 = makeToolUseBlock({ id: "3", name: "Bash", input: { command: "echo hi" } });
    const editBlock2 = makeToolUseBlock({ id: "4", name: "Write", input: { file_path: "b.ts" } });
    const bashBlock2 = makeToolUseBlock({ id: "5", name: "Bash", input: { command: "echo bye" } });
    const grepBlock: ToolResultBlock = {
      type: "tool_result",
      objectType: "ToolResultBlock",
      toolUseId: "6",
      toolName: "Grep",
      invocationString: "Grep(…)",
      content: { contentType: "generic", text: "matches" },
      isError: false,
    };

    const segments = segmentToolBlocks([editBlock1, readBlock, bashBlock1, editBlock2, bashBlock2, grepBlock]);
    expect(segments).toHaveLength(4);
    expect(segments[0].kind).toBe("chip");
    expect(segments[1].kind).toBe("tools");
    expect(segments[1].blocks).toHaveLength(2); // read + bash
    expect(segments[2].kind).toBe("chip");
    expect(segments[3].kind).toBe("tools");
    expect(segments[3].blocks).toHaveLength(2); // bash + grep
  });

  it("returns empty array for empty input", () => {
    const segments = segmentToolBlocks([]);
    expect(segments).toHaveLength(0);
  });

  it("groups all bash blocks into a single tools segment", () => {
    const bash1 = makeToolUseBlock({ id: "1", name: "Bash", input: { command: "ls" } });
    const bash2 = makeToolUseBlock({ id: "2", name: "Bash", input: { command: "pwd" } });
    const bash3 = makeToolUseBlock({ id: "3", name: "Bash", input: { command: "echo hi" } });

    const segments = segmentToolBlocks([bash1, bash2, bash3]);
    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe("tools");
    expect(segments[0].blocks).toHaveLength(3);
  });
});
