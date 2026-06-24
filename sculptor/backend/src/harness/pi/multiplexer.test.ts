import { describe, expect, it } from "vitest";

import { PiCrashError } from "~/harness/pi/errors";
import { PiTurnMultiplexer } from "~/harness/pi/multiplexer";
import { parsePiEvent, type PiEvent } from "~/harness/pi/rpc";

interface Harness {
  mux: PiTurnMultiplexer;
  emitted: Record<string, unknown>[];
  dialogs: string[];
  feed: (o: unknown) => boolean;
}

function makeHarness(abortExpected = false): Harness {
  const emitted: Record<string, unknown>[] = [];
  const dialogs: string[] = [];
  const mux = new PiTurnMultiplexer({
    emit: (m) => emitted.push(m),
    promptId: "p1",
    isAbortExpected: () => abortExpected,
    onPendingDialog: (id) => dialogs.push(id),
    now: () => 1_700_000_000_000,
  });
  const feed = (o: unknown): boolean => {
    const event = parsePiEvent(JSON.stringify(o));
    return event !== null ? mux.handleEvent(event as PiEvent) : false;
  };
  return { mux, emitted, dialogs, feed };
}

const types = (emitted: Record<string, unknown>[]): string[] =>
  emitted.map((m) => m.object_type as string);

describe("PiTurnMultiplexer", () => {
  it("streams text then finalizes the assistant message", () => {
    const h = makeHarness();
    h.feed({ type: "agent_start" });
    h.feed({
      type: "message_update",
      message: { role: "assistant", content: [] },
      assistantMessageEvent: { type: "text_delta", delta: "hello" },
    });
    h.feed({
      type: "message_end",
      message: {
        role: "assistant",
        content: [{ type: "text", text: "hello" }],
        stopReason: "stop",
      },
    });
    expect(h.feed({ type: "agent_end", messages: [], willRetry: false })).toBe(
      true,
    );

    expect(types(h.emitted)).toEqual([
      "PartialResponseBlockAgentMessage",
      "ResponseBlockAgentMessage",
    ]);
    expect(h.emitted[1]).toMatchObject({
      content: [{ object_type: "TextBlock", text: "hello" }],
    });
  });

  it("renders a tool call + result", () => {
    const h = makeHarness();
    h.feed({
      type: "message_end",
      message: {
        role: "assistant",
        content: [
          {
            type: "toolCall",
            id: "tc1",
            name: "bash",
            arguments: { command: "ls" },
          },
        ],
        stopReason: "toolUse",
      },
    });
    h.feed({
      type: "tool_execution_end",
      toolCallId: "tc1",
      toolName: "bash",
      result: "out",
      isError: false,
    });

    expect(types(h.emitted)).toEqual([
      "PartialResponseBlockAgentMessage",
      "ResponseBlockAgentMessage",
      "ResponseBlockAgentMessage",
    ]);
    const toolUse = (h.emitted[1] as { content: Record<string, unknown>[] })
      .content[0];
    expect(toolUse).toMatchObject({
      object_type: "ToolUseBlock",
      name: "Bash",
      id: "tc1",
    });
    const toolResult = (h.emitted[2] as { content: Record<string, unknown>[] })
      .content[0];
    expect(toolResult).toMatchObject({
      object_type: "ToolResultBlock",
      tool_use_id: "tc1",
      content: { content_type: "generic", text: "out" },
    });
  });

  it("surfaces a backchannel dialog as AskUserQuestion", () => {
    const h = makeHarness();
    h.feed({
      type: "extension_ui_request",
      id: "u1",
      method: "select",
      title: "Pick",
      options: ["a", "b"],
    });
    expect(h.dialogs).toEqual(["u1"]);
    expect(types(h.emitted)).toEqual(["AskUserQuestionAgentMessage"]);
    expect(h.emitted[0]).toMatchObject({
      question_data: { questions: [{ question: "Pick" }] },
    });
  });

  it("maps compaction onto the Compacting chrome", () => {
    const h = makeHarness();
    h.feed({ type: "compaction_start", reason: "threshold" });
    h.feed({ type: "compaction_end", reason: "threshold" });
    expect(types(h.emitted)).toEqual([
      "AutoCompactingAgentMessage",
      "AutoCompactingDoneAgentMessage",
    ]);
  });

  it("raises on a rejected prompt and on a terminal stopReason", () => {
    const h = makeHarness();
    expect(() =>
      h.feed({
        type: "response",
        command: "prompt",
        success: false,
        id: "p1",
        error: "no key",
      }),
    ).toThrow(PiCrashError);

    const h2 = makeHarness();
    expect(() =>
      h2.feed({
        type: "agent_end",
        messages: [
          {
            role: "assistant",
            content: [],
            stopReason: "error",
            errorMessage: "boom",
          },
        ],
        willRetry: false,
      }),
    ).toThrow(PiCrashError);
  });

  it("emits a background completion out-of-band via notify", () => {
    const h = makeHarness();
    const message = JSON.stringify({
      sculptorBackgroundTask: {
        v: 1,
        taskId: "b1",
        toolCallId: "c1",
        status: "completed",
        exitCode: 0,
        summary: "done",
        durationMs: 1000,
      },
    });
    h.feed({
      type: "extension_ui_request",
      id: "u2",
      method: "notify",
      message,
    });
    expect(types(h.emitted)).toEqual([
      "ResponseBlockAgentMessage",
      "BackgroundTaskNotificationAgentMessage",
    ]);
    expect(h.emitted[1]).toMatchObject({
      background_task_id: "b1",
      duration_seconds: 1,
    });
  });
});
