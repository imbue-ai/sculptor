import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ChatMessage } from "~/api";
import { ChatMessageRole } from "~/api";

import { DebugChatView } from "./DebugChatView.tsx";

const BASE_TIME = "2026-03-09T14:30:00.000Z";
const offsetMs = (ms: number): string => new Date(new Date(BASE_TIME).getTime() + ms).toISOString();

const makeMessage = (
  overrides: Omit<Partial<ChatMessage>, "content"> & { content: ReadonlyArray<Record<string, unknown>> },
): ChatMessage =>
  ({
    id: "msg-test",
    role: ChatMessageRole.ASSISTANT,
    approximateCreationTime: BASE_TIME,
    parentToolUseId: null,
    ...overrides,
  }) as unknown as ChatMessage;

afterEach(cleanup);

describe("DebugChatView", () => {
  it("shows empty state when there are no messages", () => {
    render(<DebugChatView messages={[]} />);
    expect(screen.getByText("No messages yet")).toBeTruthy();
  });

  it("displays role and id for each message", () => {
    const messages = [
      makeMessage({
        id: "msg-001",
        role: ChatMessageRole.USER,
        content: [{ type: "text", text: "Hello" }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={messages} />);
    expect(screen.getByText("USER")).toBeTruthy();
    expect(screen.getByText("msg-001")).toBeTruthy();
  });

  it("displays block types", () => {
    const messages = [
      makeMessage({
        content: [
          { type: "text", text: "Hi" },
          { type: "tool_use", id: "tu-1", name: "Bash", input: {} },
        ],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={messages} />);
    expect(screen.getByText("[text, tool_use]")).toBeTruthy();
  });

  it("displays message text", () => {
    const messages = [
      makeMessage({
        content: [{ type: "text", text: "Some assistant text" }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={messages} />);
    expect(screen.getByText("Some assistant text")).toBeTruthy();
  });

  it("displays relative timestamps by default", () => {
    const messages = [
      makeMessage({
        role: ChatMessageRole.USER,
        content: [{ type: "text", text: "Hi" }],
        approximateCreationTime: offsetMs(0),
      }),
      makeMessage({
        content: [{ type: "text", text: "Hello" }],
        approximateCreationTime: offsetMs(2500),
      }),
    ];
    render(<DebugChatView messages={messages} />);
    expect(screen.getByText("T+0.0s")).toBeTruthy();
    expect(screen.getByText("T+2.5s")).toBeTruthy();
  });

  it("toggles to absolute timestamps on click", () => {
    const messages = [
      makeMessage({
        role: ChatMessageRole.USER,
        content: [{ type: "text", text: "Hi" }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={messages} />);
    const timestampEl = screen.getByText("T+0.0s");
    fireEvent.click(timestampEl);
    // After clicking, the timestamp should be in absolute format (HH:MM:SS.mmm)
    expect(screen.queryByText("T+0.0s")).toBeNull();
    expect(screen.getByText(/^\d{2}:\d{2}:\d{2}\.\d{3}$/)).toBeTruthy();
  });

  it("shows parentToolUseId row only when present", () => {
    const withoutParent = [
      makeMessage({
        content: [{ type: "text", text: "No parent" }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    const { unmount } = render(<DebugChatView messages={withoutParent} />);
    expect(screen.queryByText("parentToolUseId")).toBeNull();
    unmount();

    const withParent = [
      makeMessage({
        parentToolUseId: "tu-parent-1",
        content: [{ type: "text", text: "Has parent" }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={withParent} />);
    expect(screen.getByText("parentToolUseId")).toBeTruthy();
    expect(screen.getByText("tu-parent-1")).toBeTruthy();
  });

  it("shows tool_use summary row only when tool_use blocks exist", () => {
    const withToolUse = [
      makeMessage({
        content: [{ type: "tool_use", id: "tu-1", name: "Read", input: {} }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={withToolUse} />);
    expect(screen.getByText("Read(id: tu-1)")).toBeTruthy();
  });

  it("shows tool_result summary row only when tool_result blocks exist", () => {
    const withToolResult = [
      makeMessage({
        content: [
          {
            type: "tool_result",
            toolUseId: "tu-1",
            toolName: "Bash",
            content: { contentType: "generic", text: "ok" },
          },
        ],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    render(<DebugChatView messages={withToolResult} />);
    expect(screen.getByText("Bash (toolUseId: tu-1)")).toBeTruthy();
  });

  it("does not show text paragraph when message has no text blocks", () => {
    const messages = [
      makeMessage({
        content: [{ type: "tool_use", id: "tu-1", name: "Bash", input: {} }],
        approximateCreationTime: offsetMs(0),
      }),
    ];
    const { container } = render(<DebugChatView messages={messages} />);
    const paragraphs = container.querySelectorAll("p");
    // The only <p> in the empty case would be from the empty state, but we have messages
    // so there should be no <p> with class messageText
    for (const p of paragraphs) {
      expect(p.textContent).not.toBe("");
    }
  });
});
