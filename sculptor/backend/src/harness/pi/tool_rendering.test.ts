import { describe, expect, it } from "vitest";

import {
  buildToolResultContent,
  extractTextFromToolPayload,
  mapPiToolCall,
} from "~/harness/pi/tool_rendering";

describe("mapPiToolCall", () => {
  it("maps the core tools onto Claude renderers", () => {
    expect(mapPiToolCall("read", { path: "/a" })).toEqual({
      name: "Read",
      input: { file_path: "/a" },
    });
    expect(mapPiToolCall("write", { path: "/a", content: "x" })).toEqual({
      name: "Write",
      input: { file_path: "/a", content: "x" },
    });
    expect(mapPiToolCall("bash", { command: "ls" })).toEqual({
      name: "Bash",
      input: { command: "ls" },
    });
  });

  it("maps pi edit onto Edit (single) / MultiEdit (multiple)", () => {
    expect(
      mapPiToolCall("edit", {
        path: "/a",
        edits: [{ oldText: "x", newText: "y" }],
      }),
    ).toEqual({
      name: "Edit",
      input: { file_path: "/a", old_string: "x", new_string: "y" },
    });
    expect(
      mapPiToolCall("edit", {
        path: "/a",
        edits: [
          { oldText: "x", newText: "y" },
          { oldText: "p", newText: "q" },
        ],
      }),
    ).toEqual({
      name: "MultiEdit",
      input: {
        file_path: "/a",
        edits: [
          { old_string: "x", new_string: "y" },
          { old_string: "p", new_string: "q" },
        ],
      },
    });
  });

  it("maps subagent onto Agent and passes unknown tools through", () => {
    expect(mapPiToolCall("subagent", { task: "do it" })).toEqual({
      name: "Agent",
      input: { subagent_type: "subagent", prompt: "do it" },
    });
    expect(
      mapPiToolCall("subagent", {
        tasks: [{ task: "t1", label: "L1" }, { task: "t2" }],
      }),
    ).toEqual({
      name: "Agent",
      input: {
        subagent_type: "subagent (x2)",
        prompt: "L1: t1\n\nSub-agent 2: t2",
      },
    });
    expect(mapPiToolCall("custom_tool", { foo: 1 })).toEqual({
      name: "custom_tool",
      input: { foo: 1 },
    });
  });
});

describe("tool result content", () => {
  it("extracts text from the several payload shapes", () => {
    expect(extractTextFromToolPayload("plain")).toBe("plain");
    expect(
      extractTextFromToolPayload({
        content: [
          { type: "text", text: "a" },
          { type: "text", text: "b" },
        ],
      }),
    ).toBe("ab");
    expect(extractTextFromToolPayload({ output: "out" })).toBe("out");
  });

  it("synthesizes a diff for Write and wraps pi's edit patch", () => {
    const write = buildToolResultContent(
      "Write",
      { file_path: "a.txt", content: "x\ny" },
      null,
    );
    expect(write).toMatchObject({ content_type: "diff", file_path: "a.txt" });
    expect((write as { diff: string }).diff).toContain("new file mode 100644");

    const edit = buildToolResultContent(
      "Edit",
      { file_path: "a.txt" },
      { details: { patch: "@@ -1 +1 @@\n-x\n+y" } },
    );
    expect((edit as { diff: string }).diff).toContain(
      "diff --git a/a.txt b/a.txt",
    );
    expect((edit as { diff: string }).diff).toContain("@@ -1 +1 @@");
  });

  it("falls back to generic content with fallback text", () => {
    expect(
      buildToolResultContent("Bash", { command: "ls" }, null, "fallback"),
    ).toEqual({ content_type: "generic", text: "fallback" });
  });
});
