import { describe, expect, it } from "vitest";

import type { SubagentTreeNode } from "~/pages/workspace/chatAlpha/utils/subagentTree.ts";
import type { BlockUnion } from "~/pages/workspace/utils/blockGuards.ts";

import { buildRenderGroups } from "./buildRenderGroups.ts";

const makeToolUse = (id: string, name: string): BlockUnion => ({ type: "tool_use", id, name, input: {} }) as BlockUnion;

const makeToolResult = (toolUseId: string, toolName: string): BlockUnion =>
  ({
    type: "tool_result",
    tool_use_id: toolUseId,
    toolUseId,
    toolName,
    invocationString: "",
    content: { contentType: "generic" as const, text: "ok" },
  }) as BlockUnion;

const makeText = (text: string): BlockUnion => ({ type: "text", text }) as BlockUnion;

const makeFileBlock = (source: string): BlockUnion => ({ type: "file", objectType: "FileBlock", source }) as BlockUnion;

describe("buildRenderGroups", () => {
  describe("file block grouping", () => {
    it("groups a single file block into a files group", () => {
      const content = [makeFileBlock("/tmp/photo.png")];
      const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

      const groups = buildRenderGroups(content, nodeChildren);

      expect(groups).toHaveLength(1);
      expect(groups[0]?.type).toBe("files");
      if (groups[0]?.type === "files") {
        expect(groups[0].blocks).toHaveLength(1);
        expect(groups[0].blocks[0]?.source).toBe("/tmp/photo.png");
      }
    });

    it("groups consecutive file blocks into a single files group", () => {
      const content = [makeFileBlock("/tmp/a.png"), makeFileBlock("/tmp/b.png"), makeFileBlock("/tmp/c.png")];
      const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

      const groups = buildRenderGroups(content, nodeChildren);

      expect(groups).toHaveLength(1);
      expect(groups[0]?.type).toBe("files");
      if (groups[0]?.type === "files") {
        expect(groups[0].blocks).toHaveLength(3);
      }
    });

    it("separates file blocks when interleaved with text blocks", () => {
      const content = [makeFileBlock("/tmp/a.png"), makeText("Some text"), makeFileBlock("/tmp/b.png")];
      const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

      const groups = buildRenderGroups(content, nodeChildren);

      expect(groups).toHaveLength(3);
      expect(groups[0]?.type).toBe("files");
      expect(groups[1]?.type).toBe("text");
      expect(groups[2]?.type).toBe("files");
      if (groups[0]?.type === "files") {
        expect(groups[0].blocks).toHaveLength(1);
      }

      if (groups[2]?.type === "files") {
        expect(groups[2].blocks).toHaveLength(1);
      }
    });

    it("separates file blocks from adjacent tool blocks", () => {
      const content = [makeToolUse("tu_1", "Read"), makeFileBlock("/tmp/photo.png")];
      const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

      const groups = buildRenderGroups(content, nodeChildren);

      expect(groups).toHaveLength(2);
      expect(groups[0]?.type).toBe("tools");
      expect(groups[1]?.type).toBe("files");
    });

    it("groups files preceded by text and followed by tools into distinct groups", () => {
      const content = [
        makeText("Here are the images:"),
        makeFileBlock("/tmp/a.png"),
        makeFileBlock("/tmp/b.png"),
        makeToolUse("tu_1", "Read"),
      ];
      const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

      const groups = buildRenderGroups(content, nodeChildren);

      expect(groups).toHaveLength(3);
      expect(groups[0]?.type).toBe("text");
      expect(groups[1]?.type).toBe("files");
      expect(groups[2]?.type).toBe("tools");
      if (groups[1]?.type === "files") {
        expect(groups[1].blocks).toHaveLength(2);
      }
    });
  });

  it("keeps an Agent tool_use grouped with adjacent tool blocks", () => {
    // SCU-1139: when the LLM emits parallel tools alongside an Agent call
    // in one message, the Agent block must NOT split the surrounding tools
    // into separate groups. ToolBlockGroup pulls the subagent block out at
    // render time and renders the AlphaSubagentPill above the pill row.
    const content = [makeToolUse("tu_read", "Read"), makeToolUse("tu_agent", "Agent")];
    const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

    const groups = buildRenderGroups(content, nodeChildren);

    const toolGroups = groups.filter((g) => g.type === "tools");
    expect(toolGroups).toHaveLength(1);
    if (toolGroups[0]?.type === "tools") {
      expect(toolGroups[0].blocks).toHaveLength(2);
    }
  });

  it("keeps a Task tool_use grouped with adjacent tool blocks", () => {
    const content = [makeToolUse("tu_edit", "Edit"), makeToolUse("tu_task", "Task")];
    const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

    const groups = buildRenderGroups(content, nodeChildren);

    const toolGroups = groups.filter((g) => g.type === "tools");
    expect(toolGroups).toHaveLength(1);
    if (toolGroups[0]?.type === "tools") {
      expect(toolGroups[0].blocks).toHaveLength(2);
    }
  });

  it("keeps an Agent block grouped even when nodeChildren has entries (sub-bash present)", () => {
    const content = [makeToolUse("tu_read", "Read"), makeToolUse("tu_agent", "Agent")];
    const nodeChildren = new Map<string, Array<SubagentTreeNode>>();
    nodeChildren.set("tu_agent", [{ message: {} as SubagentTreeNode["message"], children: new Map() }]);

    const groups = buildRenderGroups(content, nodeChildren);

    const toolGroups = groups.filter((g) => g.type === "tools");
    expect(toolGroups).toHaveLength(1);
    if (toolGroups[0]?.type === "tools") {
      expect(toolGroups[0].blocks).toHaveLength(2);
    }
  });

  it("keeps parallel Bash tools grouped when an Agent appears in the middle (SCU-1139)", () => {
    // Reproduces the bug scenario: primary message has [Bash, Bash, Agent, Bash, Bash, Bash].
    // All Bash blocks must be in one group so they render as one pill row;
    // ToolBlockGroup will hoist the Agent block out as a separate AlphaSubagentPill.
    const content = [
      makeToolUse("bash_1", "Bash"),
      makeToolUse("bash_2", "Bash"),
      makeToolUse("agent_1", "Agent"),
      makeToolUse("bash_3", "Bash"),
      makeToolUse("bash_4", "Bash"),
      makeToolUse("bash_5", "Bash"),
    ];
    const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

    const groups = buildRenderGroups(content, nodeChildren);

    const toolGroups = groups.filter((g) => g.type === "tools");
    expect(toolGroups).toHaveLength(1);
    if (toolGroups[0]?.type === "tools") {
      expect(toolGroups[0].blocks).toHaveLength(6);
    }
  });

  it("skips subagent tool_result blocks when tool name is in SUBAGENT_TOOL_NAMES", () => {
    // Agent tool_result should be skipped even without children
    const content = [makeToolResult("tu_agent", "Agent"), makeToolUse("tu_read", "Read")];
    const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

    const groups = buildRenderGroups(content, nodeChildren);

    // The Agent tool_result should be skipped, leaving only the Read tool_use
    const toolGroups = groups.filter((g) => g.type === "tools");
    expect(toolGroups).toHaveLength(1);
    expect(toolGroups[0]?.type === "tools" && toolGroups[0].blocks).toHaveLength(1);
  });

  it("groups adjacent non-subagent tool blocks together", () => {
    const content = [makeText("hi"), makeToolUse("tu_1", "Read"), makeToolUse("tu_2", "Write")];
    const nodeChildren = new Map<string, Array<SubagentTreeNode>>();

    const groups = buildRenderGroups(content, nodeChildren);

    expect(groups).toHaveLength(2);
    expect(groups[0]?.type).toBe("text");
    expect(groups[1]?.type).toBe("tools");
    if (groups[1]?.type === "tools") {
      expect(groups[1].blocks).toHaveLength(2);
    }
  });
});
