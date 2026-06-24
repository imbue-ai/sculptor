import { describe, expect, it } from "vitest";

import {
  createToolContent,
  extractMediaTagsFromText,
  getToolInvocationString,
  parseClaudeLine,
  splitTextAndMedia,
  type ToolUseMap,
} from "~/harness/claude/stream_parser";

const emptyMap = (): ToolUseMap => new Map();

describe("parseClaudeLine — stream events", () => {
  it("parses message_start with parent_tool_use_id", () => {
    const result = parseClaudeLine(
      JSON.stringify({
        type: "stream_event",
        parent_tool_use_id: "tu_1",
        event: { type: "message_start", message: { id: "asst_1" } },
      }),
      emptyMap(),
    );
    expect(result).toEqual({
      event: {
        kind: "message_start",
        messageId: "asst_1",
        parentToolUseId: "tu_1",
      },
    });
  });

  it("parses text + tool deltas and stops", () => {
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: {
            type: "content_block_start",
            index: 0,
            content_block: { type: "text" },
          },
        }),
        emptyMap(),
      ),
    ).toEqual({ event: { kind: "text_block_start", index: 0 } });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: {
            type: "content_block_start",
            index: 1,
            content_block: { type: "tool_use", id: "tu_1", name: "Bash" },
          },
        }),
        emptyMap(),
      ),
    ).toEqual({
      event: {
        kind: "tool_block_start",
        index: 1,
        toolId: "tu_1",
        toolName: "Bash",
      },
    });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: {
            type: "content_block_delta",
            index: 0,
            delta: { type: "text_delta", text: "hi" },
          },
        }),
        emptyMap(),
      ),
    ).toEqual({ event: { kind: "text_delta", index: 0, text: "hi" } });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: {
            type: "content_block_delta",
            index: 1,
            delta: { type: "input_json_delta", partial_json: "{" },
          },
        }),
        emptyMap(),
      ),
    ).toEqual({
      event: { kind: "tool_input_delta", index: 1, partialJson: "{" },
    });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: { type: "content_block_stop", index: 1 },
        }),
        emptyMap(),
      ),
    ).toEqual({ event: { kind: "content_block_stop", index: 1 } });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: { type: "message_stop" },
        }),
        emptyMap(),
      ),
    ).toEqual({ event: { kind: "message_stop" } });
  });

  it("drops unhandled block/delta types (e.g. thinking)", () => {
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: {
            type: "content_block_start",
            index: 0,
            content_block: { type: "thinking" },
          },
        }),
        emptyMap(),
      ),
    ).toBeNull();
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "stream_event",
          event: {
            type: "content_block_delta",
            index: 0,
            delta: { type: "thinking_delta" },
          },
        }),
        emptyMap(),
      ),
    ).toBeNull();
  });
});

describe("parseClaudeLine — responses", () => {
  it("parses system/init session id", () => {
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "system",
          subtype: "init",
          session_id: "sess_9",
        }),
        emptyMap(),
      ),
    ).toEqual({ response: { kind: "init", sessionId: "sess_9" } });
  });

  it("parses an assistant message with text + tool_use, extracting media", () => {
    const result = parseClaudeLine(
      JSON.stringify({
        type: "assistant",
        parent_tool_use_id: null,
        message: {
          id: "asst_1",
          content: [
            { type: "text", text: 'see <img src="/tmp/a.png">' },
            {
              type: "tool_use",
              id: "tu_1",
              name: "Read",
              input: { file_path: "/x" },
            },
          ],
        },
      }),
      emptyMap(),
    );
    expect(result).toEqual({
      response: {
        kind: "assistant",
        messageId: "asst_1",
        parentToolUseId: null,
        contentBlocks: [
          { object_type: "TextBlock", type: "text", text: "see" },
          { object_type: "FileBlock", type: "file", source: "/tmp/a.png" },
          {
            object_type: "ToolUseBlock",
            type: "tool_use",
            id: "tu_1",
            name: "Read",
            input: { file_path: "/x" },
            interactive_role: null,
          },
        ],
      },
    });
  });

  it("parses a user tool-result frame into a ToolResultBlock with generic content", () => {
    const map: ToolUseMap = new Map([
      ["tu_1", { name: "Bash", input: { command: "ls" } }],
    ]);
    const result = parseClaudeLine(
      JSON.stringify({
        type: "user",
        message: {
          content: [
            {
              type: "tool_result",
              tool_use_id: "tu_1",
              content: "file.txt",
              is_error: false,
            },
          ],
        },
      }),
      map,
    );
    expect(result).not.toBeNull();
    const block = (
      result as { response: { contentBlocks: Record<string, unknown>[] } }
    ).response.contentBlocks[0];
    expect(block).toMatchObject({
      object_type: "ToolResultBlock",
      tool_use_id: "tu_1",
      tool_name: "Bash",
      invocation_string: "ls",
      is_error: false,
      content: { content_type: "generic", text: "file.txt" },
    });
  });

  it("drops plain-text user echoes", () => {
    expect(
      parseClaudeLine(
        JSON.stringify({ type: "user", message: { content: "just text" } }),
        emptyMap(),
      ),
    ).toBeNull();
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "user",
          message: { content: [{ type: "text", text: "hi" }] },
        }),
        emptyMap(),
      ),
    ).toBeNull();
  });

  it("captures ScheduleWakeup metadata", () => {
    const map: ToolUseMap = new Map([
      ["tu_1", { name: "ScheduleWakeup", input: {} }],
    ]);
    const result = parseClaudeLine(
      JSON.stringify({
        type: "user",
        tool_use_result: { scheduledFor: 1700000000000 },
        message: {
          content: [
            { type: "tool_result", tool_use_id: "tu_1", content: "ok" },
          ],
        },
      }),
      map,
    );
    expect(
      (result as { response: { scheduledWakeupFor: number | null } }).response
        .scheduledWakeupFor,
    ).toBe(1700000000000);
  });

  it("parses a result message with token usage", () => {
    const result = parseClaudeLine(
      JSON.stringify({
        type: "result",
        is_error: false,
        result: "done",
        duration_ms: 1234,
        usage: { input_tokens: 10, output_tokens: 5 },
        total_cost_usd: 0.01,
      }),
      emptyMap(),
    );
    expect(result).toEqual({
      response: {
        kind: "end",
        isError: false,
        result: "done",
        durationMs: 1234,
        inputTokens: 10,
        outputTokens: 5,
        totalCostUsd: 0.01,
        sessionId: null,
      },
    });
  });

  it("parses background task lifecycle frames", () => {
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "system",
          subtype: "task_started",
          task_id: "t1",
          tool_use_id: "tu_1",
          description: "d",
          task_type: "local_bash",
        }),
        emptyMap(),
      ),
    ).toEqual({
      response: {
        kind: "task_started",
        taskId: "t1",
        toolUseId: "tu_1",
        description: "d",
        taskType: "local_bash",
      },
    });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "system",
          subtype: "task_notification",
          task_id: "t1",
          tool_use_id: "tu_1",
          status: "completed",
          summary: "s",
          usage: { duration_ms: 2000 },
        }),
        emptyMap(),
      ),
    ).toEqual({
      response: {
        kind: "task_notification",
        taskId: "t1",
        toolUseId: "tu_1",
        status: "completed",
        summary: "s",
        durationMs: 2000,
      },
    });
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "system",
          subtype: "task_updated",
          task_id: "t1",
          patch: { status: "completed" },
        }),
        emptyMap(),
      ),
    ).toEqual({
      response: { kind: "task_updated", taskId: "t1", status: "completed" },
    });
  });

  it("ignores unknown/system-status lines and throws on invalid JSON", () => {
    expect(
      parseClaudeLine(
        JSON.stringify({
          type: "system",
          subtype: "status",
          status: "compacting",
        }),
        emptyMap(),
      ),
    ).toBeNull();
    expect(parseClaudeLine("", emptyMap())).toBeNull();
    expect(() => parseClaudeLine("{not json", emptyMap())).toThrow();
  });
});

describe("media helpers", () => {
  it("extractMediaTagsFromText strips local media and returns paths", () => {
    expect(
      extractMediaTagsFromText(
        'a <img src="/x/y.png"> b <img src="http://z.png"> c',
      ),
    ).toEqual({
      cleanedText: 'a  b <img src="http://z.png"> c',
      filePaths: ["/x/y.png"],
    });
  });

  it("splitTextAndMedia preserves order", () => {
    expect(splitTextAndMedia('intro <video src="/v/clip.mp4"> outro')).toEqual([
      { object_type: "TextBlock", type: "text", text: "intro" },
      { object_type: "FileBlock", type: "file", source: "/v/clip.mp4" },
      { object_type: "TextBlock", type: "text", text: "outro" },
    ]);
  });
});

describe("tool content synthesis", () => {
  it("synthesizes a new-file diff for a successful Write", () => {
    const content = createToolContent(
      "Write",
      { file_path: "a.txt", content: "x\ny" },
      "ok",
      false,
    );
    expect(content).toEqual({
      content_type: "diff",
      file_path: "a.txt",
      diff: expect.stringContaining("new file mode 100644"),
    });
  });

  it("keeps generic content for a failed Write", () => {
    const content = createToolContent(
      "Write",
      { file_path: "a.txt", content: "x" },
      "error text",
      true,
    );
    expect(content).toEqual({ content_type: "generic", text: "error text" });
  });

  it("derives invocation strings per tool", () => {
    expect(getToolInvocationString("Bash", { command: "ls -la" })).toBe(
      "ls -la",
    );
    expect(
      getToolInvocationString("Grep", { pattern: "foo", path: "src" }),
    ).toBe('"foo" in src');
    expect(getToolInvocationString("Read", { file_path: "/a/b" })).toBe("/a/b");
  });
});
