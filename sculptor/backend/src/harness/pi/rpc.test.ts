import { describe, expect, it } from "vitest";

import {
  buildExtensionUiResponseCommand,
  buildPromptCommand,
  buildSetModelCommand,
  extractAssistantText,
  humanizePiFailureReason,
  parsePiEvent,
} from "~/harness/pi/rpc";

describe("parsePiEvent", () => {
  it("parses the three lanes", () => {
    expect(
      parsePiEvent(
        JSON.stringify({
          type: "response",
          command: "prompt",
          success: false,
          id: "p1",
          error: "boom",
        }),
      ),
    ).toEqual({
      kind: "response",
      command: "prompt",
      success: false,
      id: "p1",
      error: "boom",
      data: null,
    });
    expect(
      parsePiEvent(
        JSON.stringify({
          type: "extension_ui_request",
          id: "u1",
          method: "select",
          title: "T",
          options: ["a", "b"],
        }),
      ),
    ).toMatchObject({
      kind: "extension_ui_request",
      id: "u1",
      method: "select",
      options: ["a", "b"],
    });
    expect(
      parsePiEvent(
        JSON.stringify({ type: "agent_end", messages: [], willRetry: false }),
      ),
    ).toEqual({ kind: "agent_end", messages: [], willRetry: false });
  });

  it("parses streaming + tool-execution events", () => {
    expect(
      parsePiEvent(
        JSON.stringify({
          type: "message_update",
          message: { role: "assistant", content: [] },
          assistantMessageEvent: { type: "text_delta", delta: "hi" },
        }),
      ),
    ).toMatchObject({
      kind: "message_update",
      assistantMessageEvent: { type: "text_delta", delta: "hi" },
    });
    expect(
      parsePiEvent(
        JSON.stringify({
          type: "tool_execution_end",
          toolCallId: "t1",
          toolName: "bash",
          result: "ok",
          isError: false,
        }),
      ),
    ).toEqual({
      kind: "tool_execution_end",
      toolCallId: "t1",
      toolName: "bash",
      result: "ok",
      isError: false,
    });
  });

  it("returns null for blank/non-JSON and unknown for unrecognized types", () => {
    expect(parsePiEvent("")).toBeNull();
    expect(parsePiEvent("{bad")).toBeNull();
    expect(parsePiEvent(JSON.stringify({ type: "queue_update" }))).toEqual({
      kind: "unknown",
    });
  });
});

describe("command builders", () => {
  it("frames prompt / set_model / extension_ui_response", () => {
    expect(JSON.parse(buildPromptCommand("p1", "hello"))).toEqual({
      type: "prompt",
      id: "p1",
      message: "hello",
    });
    expect(JSON.parse(buildSetModelCommand("s1", "anthropic", "m1"))).toEqual({
      type: "set_model",
      id: "s1",
      provider: "anthropic",
      modelId: "m1",
    });
    expect(
      JSON.parse(buildExtensionUiResponseCommand("u1", { value: "A" })),
    ).toEqual({ type: "extension_ui_response", id: "u1", value: "A" });
  });
});

describe("helpers", () => {
  it("extracts assistant text and humanizes failure reasons", () => {
    expect(
      extractAssistantText({
        role: "assistant",
        content: [
          { type: "text", text: "a" },
          { type: "toolCall" },
          { type: "text", text: "b" },
        ],
        stopReason: null,
        model: null,
        errorMessage: null,
      }),
    ).toBe("ab");
    expect(humanizePiFailureReason("401 unauthorized")).toMatch(
      /require authentication/,
    );
    expect(humanizePiFailureReason("model not found: x")).toMatch(
      /may not exist/,
    );
    expect(humanizePiFailureReason("")).toMatch(/failed to complete/);
    expect(humanizePiFailureReason("plain reason")).toBe("plain reason");
  });
});
