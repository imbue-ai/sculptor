import { describe, expect, it } from "vitest";

import {
  buildChildContentBlocks,
  parseSubagentCompletion,
  parseSubagentStart,
  SUBAGENT_NOTIFY_MARKER,
} from "~/harness/pi/subagent";

describe("parseSubagentStart", () => {
  it("parses a version-matched launch snapshot", () => {
    const result = {
      details: {
        v: 1,
        task: {
          taskId: "tk1",
          toolCallId: "tc1",
          label: "build",
          pgids: [101, -2],
          count: 2,
          status: "running",
        },
      },
    };
    expect(parseSubagentStart(result)).toEqual({
      taskId: "tk1",
      toolCallId: "tc1",
      label: "build",
      pgids: [101],
      count: 2,
      status: "running",
    });
  });

  it("rejects wrong version / missing ids", () => {
    expect(
      parseSubagentStart({
        details: { v: 2, task: { taskId: "t", toolCallId: "c" } },
      }),
    ).toBeNull();
    expect(parseSubagentStart({ details: { v: 1, task: {} } })).toBeNull();
    expect(parseSubagentStart("nope")).toBeNull();
  });
});

describe("parseSubagentCompletion + buildChildContentBlocks", () => {
  it("parses the notify marker and sorts child events by seq", () => {
    const payload = {
      [SUBAGENT_NOTIFY_MARKER]: {
        v: 1,
        taskId: "tk1",
        toolCallId: "tc1",
        status: "completed",
        children: [
          {
            childId: "c1",
            label: "child",
            status: "done",
            events: [
              { seq: 2, kind: "text", text: "second" },
              {
                seq: 1,
                kind: "tool_call",
                toolCallId: "x",
                toolName: "read",
                args: { path: "/a" },
              },
            ],
          },
        ],
      },
    };
    const completion = parseSubagentCompletion(JSON.stringify(payload));
    expect(completion).not.toBeNull();
    const child = completion!.children[0]!;
    expect(child.events.map((e) => e.seq)).toEqual([1, 2]);

    const blocks = buildChildContentBlocks(child, "tc1");
    expect(blocks[0]).toMatchObject({
      object_type: "ToolUseBlock",
      name: "Read",
      id: "tc1:c1:x",
    });
    expect(blocks[1]).toMatchObject({
      object_type: "TextBlock",
      text: "second",
    });
  });

  it("returns null for a non-subagent notify", () => {
    expect(
      parseSubagentCompletion(JSON.stringify({ somethingElse: {} })),
    ).toBeNull();
    expect(parseSubagentCompletion("not json")).toBeNull();
  });

  it("renders a placeholder bubble for an empty child", () => {
    const blocks = buildChildContentBlocks(
      {
        childId: "c1",
        label: "child",
        task: "",
        status: "error",
        stopReason: "boom",
        exitCode: 1,
        events: [],
      },
      "tc1",
    );
    expect(blocks[0]).toMatchObject({ object_type: "TextBlock" });
    expect((blocks[0] as { text: string }).text).toContain("failed");
  });
});
