import { beforeEach, describe, expect, it } from "vitest";

import { SculptorMcpServer } from "~/harness/claude/mcp";
import { ClaudeOutputProcessor } from "~/harness/claude/output_processor";

interface Harness {
  processor: ClaudeOutputProcessor;
  emitted: Record<string, unknown>[];
  stdin: string[];
  sessionIds: string[];
}

function makeHarness(): Harness {
  const emitted: Record<string, unknown>[] = [];
  const stdin: string[] = [];
  const sessionIds: string[] = [];
  const mcpServer = new SculptorMcpServer(() => undefined);
  const processor = new ClaudeOutputProcessor({
    emit: (m) => emitted.push(m),
    writeStdin: (line) => stdin.push(line),
    mcpServer,
    onSessionId: (sid) => sessionIds.push(sid),
    now: () => 1_700_000_000_000,
  });
  mcpServer.setRespond((reqId, data) =>
    stdin.push(
      JSON.stringify({
        type: "control_response",
        response: { subtype: "success", request_id: reqId, response: data },
      }) + "\n",
    ),
  );
  return { processor, emitted, stdin, sessionIds };
}

const types = (emitted: Record<string, unknown>[]): string[] =>
  emitted.map((m) => m.object_type as string);

describe("ClaudeOutputProcessor — streamed turn", () => {
  let h: Harness;
  beforeEach(() => {
    h = makeHarness();
  });

  it("emits partial → streaming-complete → persistence → turn metrics", () => {
    const feed = (o: unknown): void =>
      h.processor.processLine(JSON.stringify(o));
    feed({ type: "system", subtype: "init", session_id: "sess_1" });
    feed({
      type: "stream_event",
      event: { type: "message_start", message: { id: "asst_1" } },
    });
    feed({
      type: "stream_event",
      event: {
        type: "content_block_start",
        index: 0,
        content_block: { type: "text" },
      },
    });
    feed({
      type: "stream_event",
      event: {
        type: "content_block_delta",
        index: 0,
        delta: { type: "text_delta", text: "hello" },
      },
    });
    feed({
      type: "assistant",
      message: { id: "asst_1", content: [{ type: "text", text: "hello" }] },
    });
    feed({
      type: "stream_event",
      event: { type: "content_block_stop", index: 0 },
    });
    feed({ type: "stream_event", event: { type: "message_stop" } });
    feed({
      type: "result",
      is_error: false,
      result: "ok",
      usage: { input_tokens: 10, output_tokens: 5 },
    });

    expect(h.sessionIds).toEqual(["sess_1"]);
    expect(types(h.emitted)).toEqual([
      "PartialResponseBlockAgentMessage",
      "StreamingMessageCompleteAgentMessage",
      "ResponseBlockAgentMessage",
      "TurnMetricsAgentMessage",
    ]);
    const persistence = h.emitted.find(
      (m) => m.object_type === "ResponseBlockAgentMessage",
    );
    expect(persistence).toMatchObject({
      assistant_message_id: "asst_1",
      content: [{ object_type: "TextBlock", text: "hello" }],
    });
    const metrics = h.emitted.find(
      (m) => m.object_type === "TurnMetricsAgentMessage",
    );
    expect(metrics).toMatchObject({
      turn_metrics: { input_tokens: 10, output_tokens: 5 },
    });
    expect(h.processor.isTurnComplete()).toBe(true);
    expect(h.processor.turnError).toBeUndefined();
  });

  it("emits a non-streamed assistant + tool result", () => {
    const feed = (o: unknown): void =>
      h.processor.processLine(JSON.stringify(o));
    feed({
      type: "assistant",
      message: {
        id: "asst_1",
        content: [
          {
            type: "tool_use",
            id: "tu_1",
            name: "Bash",
            input: { command: "ls" },
          },
        ],
      },
    });
    feed({
      type: "user",
      message: {
        content: [
          {
            type: "tool_result",
            tool_use_id: "tu_1",
            content: "out",
            is_error: false,
          },
        ],
      },
    });
    expect(types(h.emitted)).toEqual([
      "ResponseBlockAgentMessage",
      "ResponseBlockAgentMessage",
    ]);
    const toolResult = h.emitted[1] as { content: { object_type: string }[] };
    expect(toolResult.content[0]).toMatchObject({
      object_type: "ToolResultBlock",
      tool_use_id: "tu_1",
      tool_name: "Bash",
    });
  });
});

describe("ClaudeOutputProcessor — control protocol", () => {
  it("auto-approves can_use_tool permission requests", () => {
    const h = makeHarness();
    h.processor.processLine(
      JSON.stringify({
        type: "control_request",
        request_id: "c1",
        request: {
          subtype: "can_use_tool",
          tool_name: "Bash",
          input: { command: "ls" },
        },
      }),
    );
    expect(h.emitted).toHaveLength(0);
    const response = JSON.parse(h.stdin[0] as string);
    expect(response).toMatchObject({
      type: "control_response",
      response: {
        request_id: "c1",
        response: { behavior: "allow", updatedInput: { command: "ls" } },
      },
    });
  });

  it("routes mcp_message initialize into the MCP server", () => {
    const h = makeHarness();
    h.processor.processLine(
      JSON.stringify({
        type: "control_request",
        request_id: "c2",
        request: {
          subtype: "mcp_message",
          server_name: "sculptor",
          message: { method: "initialize", id: 1 },
        },
      }),
    );
    const response = JSON.parse(h.stdin[0] as string);
    expect(response.response.response.mcp_response.result.serverInfo.name).toBe(
      "sculptor",
    );
  });

  it("shows the PreCompact indicator on a hook callback", () => {
    const h = makeHarness();
    h.processor.processLine(
      JSON.stringify({
        type: "control_request",
        request_id: "c3",
        request: {
          subtype: "hook_callback",
          callback_id: "sculptor_pre_compact",
        },
      }),
    );
    expect(types(h.emitted)).toEqual(["AutoCompactingAgentMessage"]);
  });
});

describe("ClaudeOutputProcessor — interception, compaction, errors", () => {
  it("intercepts an MCP ask_user_question tool call", () => {
    const h = makeHarness();
    const question = {
      question: "Q",
      header: "H",
      options: [
        { label: "A", description: "x" },
        { label: "B", description: "y" },
      ],
      multiSelect: false,
    };
    const toolUse = {
      type: "tool_use",
      id: "tu_1",
      name: "mcp__sculptor__ask_user_question",
      input: { questions: [question] },
    };
    h.processor.processLine(
      JSON.stringify({
        type: "assistant",
        message: { id: "asst_1", content: [toolUse] },
      }),
    );
    const auq = h.emitted.find(
      (m) => m.object_type === "AskUserQuestionAgentMessage",
    );
    expect(auq).toMatchObject({ question_data: { tool_use_id: "tu_1" } });
  });

  it("emits a context summary when compaction completes", () => {
    const h = makeHarness();
    h.processor.processLine(
      JSON.stringify({
        type: "system",
        subtype: "status",
        status: "compacting",
      }),
    );
    h.processor.processLine(
      JSON.stringify({
        type: "user",
        isSynthetic: true,
        message: { content: "summary text" },
      }),
    );
    expect(types(h.emitted)).toEqual([
      "AutoCompactingAgentMessage",
      "AutoCompactingDoneAgentMessage",
      "ContextSummaryMessage",
    ]);
    const summary = h.emitted.find(
      (m) => m.object_type === "ContextSummaryMessage",
    );
    expect(summary).toMatchObject({ content: "summary text" });
  });

  it("tracks background tasks and keeps the turn open until they finish", () => {
    const h = makeHarness();
    const feed = (o: unknown): void =>
      h.processor.processLine(JSON.stringify(o));
    feed({
      type: "system",
      subtype: "task_started",
      task_id: "t1",
      tool_use_id: "tu_1",
    });
    feed({
      type: "result",
      is_error: false,
      result: "ok",
      usage: { input_tokens: 1, output_tokens: 1 },
    });
    expect(h.processor.isTurnComplete()).toBe(false);
    feed({
      type: "system",
      subtype: "task_notification",
      task_id: "t1",
      tool_use_id: "tu_1",
      status: "completed",
    });
    expect(h.processor.pendingBackgroundTasks.size).toBe(0);
  });

  it("surfaces a transient error for an API 429 result", () => {
    const h = makeHarness();
    h.processor.processLine(
      JSON.stringify({
        type: "result",
        is_error: true,
        result: "API Error: 429 rate limited",
      }),
    );
    expect(h.processor.turnError).toMatchObject({ transient: true });
  });

  it("warns on a malformed (non-JSON) line", () => {
    const h = makeHarness();
    h.processor.processLine("{ this is not json");
    expect(types(h.emitted)).toEqual(["WarningAgentMessage"]);
  });
});
