import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "~/api";
import { ChatMessageRole } from "~/api";

import { useJumpToBottom } from "../useJumpToBottom.ts";

const makeMessage = (role: ChatMessageRole, id: string): ChatMessage =>
  ({
    id,
    role,
    content: [{ type: "text", text: "hello" }],
    approximateCreationTime: "2024-01-01T00:00:00Z",
  }) as ChatMessage;

describe("useJumpToBottom", () => {
  // The hook requires at least one message to show the button (hasMessages guard).
  const oneMessage: ReadonlyArray<ChatMessage> = [makeMessage(ChatMessageRole.ASSISTANT, "seed")];

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("is hidden when at bottom", () => {
    const { result } = renderHook(() => useJumpToBottom(true, oneMessage, false, false));
    expect(result.current.isVisible).toBe(false);
  });

  it("is hidden when there are no messages", () => {
    const { result } = renderHook(() => useJumpToBottom(false, [], false, false));
    expect(result.current.isVisible).toBe(false);

    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(false);
  });

  it("becomes visible after 150ms debounce when not at bottom", () => {
    const { result } = renderHook(() => useJumpToBottom(false, oneMessage, false, false));

    // Not visible immediately
    expect(result.current.isVisible).toBe(false);

    // Visible after debounce
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);
  });

  it("does not become visible if returning to bottom within debounce period", () => {
    const { result, rerender } = renderHook(({ isAtBottom }) => useJumpToBottom(isAtBottom, oneMessage, false, false), {
      initialProps: { isAtBottom: false },
    });

    // Advance partway through debounce
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.isVisible).toBe(false);

    // Return to bottom before debounce completes
    rerender({ isAtBottom: true });
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.isVisible).toBe(false);
  });

  it("hides immediately when reaching bottom", () => {
    const { result, rerender } = renderHook(({ isAtBottom }) => useJumpToBottom(isAtBottom, oneMessage, false, false), {
      initialProps: { isAtBottom: false },
    });

    // Show the button
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);

    // Return to bottom — hide immediately
    rerender({ isAtBottom: true });
    expect(result.current.isVisible).toBe(false);
  });

  it("has jump label when no unseen content", () => {
    const { result } = renderHook(() => useJumpToBottom(false, oneMessage, false, false));
    // User started not-at-bottom with the same message count — no new content
    expect(result.current.label).toBe("jump");
  });

  it("shows new label when streaming while scrolled away", () => {
    const { result, rerender } = renderHook(
      ({ isAtBottom, isStreaming }) => useJumpToBottom(isAtBottom, oneMessage, isStreaming, false),
      {
        initialProps: { isAtBottom: false, isStreaming: false },
      },
    );

    expect(result.current.label).toBe("jump");

    // Start streaming while scrolled away
    rerender({ isAtBottom: false, isStreaming: true });
    expect(result.current.label).toBe("new");
  });

  it("reverts to jump label when streaming stops and no new messages", () => {
    const { result, rerender } = renderHook(
      ({ isAtBottom, isStreaming }) => useJumpToBottom(isAtBottom, oneMessage, isStreaming, false),
      {
        initialProps: { isAtBottom: false, isStreaming: true },
      },
    );

    expect(result.current.label).toBe("new");

    // Stop streaming (no new messages added)
    rerender({ isAtBottom: false, isStreaming: false });
    expect(result.current.label).toBe("jump");
  });

  it("shows jump label when new messages arrive without streaming", () => {
    const messages1: ReadonlyArray<ChatMessage> = [makeMessage(ChatMessageRole.ASSISTANT, "m1")];
    const messages2: ReadonlyArray<ChatMessage> = [
      makeMessage(ChatMessageRole.ASSISTANT, "m1"),
      makeMessage(ChatMessageRole.ASSISTANT, "m2"),
    ];

    const { result, rerender } = renderHook(
      ({ isAtBottom, messages }) => useJumpToBottom(isAtBottom, messages, false, false),
      {
        initialProps: { isAtBottom: true, messages: messages1 },
      },
    );

    expect(result.current.label).toBe("jump");

    // User scrolls away, new message arrives (no streaming) — still "jump"
    rerender({ isAtBottom: false, messages: messages2 });
    expect(result.current.label).toBe("jump");
  });

  it("shows new label again after user scrolls away from bottom during streaming", () => {
    const { result, rerender } = renderHook(
      ({ isAtBottom, isStreaming }) => useJumpToBottom(isAtBottom, oneMessage, isStreaming, false),
      {
        initialProps: { isAtBottom: true, isStreaming: true },
      },
    );

    // User at bottom during streaming — label is "new" (streaming) but button hidden
    expect(result.current.isVisible).toBe(false);

    // User scrolls away while streaming continues
    rerender({ isAtBottom: false, isStreaming: true });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);
    expect(result.current.label).toBe("new");

    // User scrolls back to bottom
    rerender({ isAtBottom: true, isStreaming: true });
    expect(result.current.isVisible).toBe(false);

    // User scrolls away again — should still say "new" because streaming
    rerender({ isAtBottom: false, isStreaming: true });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);
    expect(result.current.label).toBe("new");
  });

  it("is hidden when isJumpSuppressed is true even when not at bottom with messages", () => {
    const { result } = renderHook(() => useJumpToBottom(false, oneMessage, false, true));

    // Not visible immediately
    expect(result.current.isVisible).toBe(false);

    // Still not visible after debounce period
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(false);
  });

  it("becomes visible after suppression clears and debounce elapses", () => {
    const { result, rerender } = renderHook(
      ({ isJumpSuppressed }) => useJumpToBottom(false, oneMessage, false, isJumpSuppressed),
      {
        initialProps: { isJumpSuppressed: true },
      },
    );

    // Suppressed — not visible even after debounce
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(false);

    // Clear suppression
    rerender({ isJumpSuppressed: false });
    expect(result.current.isVisible).toBe(false);

    // Visible after the new debounce elapses
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);
  });

  it("clears pending debounce timer when suppression activates", () => {
    const { result, rerender } = renderHook(
      ({ isJumpSuppressed }) => useJumpToBottom(false, oneMessage, false, isJumpSuppressed),
      {
        initialProps: { isJumpSuppressed: false },
      },
    );

    // Advance partway through debounce
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.isVisible).toBe(false);

    // Activate suppression before debounce completes
    rerender({ isJumpSuppressed: true });

    // Let the original debounce period expire — button should stay hidden
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.isVisible).toBe(false);
  });

  it("label updates correctly across suppression and streaming changes", () => {
    const { result, rerender } = renderHook(
      ({ isJumpSuppressed, isStreaming }) => useJumpToBottom(false, oneMessage, isStreaming, isJumpSuppressed),
      {
        initialProps: { isJumpSuppressed: false, isStreaming: false },
      },
    );

    // Make button visible
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);
    expect(result.current.label).toBe("jump");

    // Start streaming — label changes to "new"
    rerender({ isJumpSuppressed: false, isStreaming: true });
    expect(result.current.label).toBe("new");

    // Activate suppression — button hides
    rerender({ isJumpSuppressed: true, isStreaming: true });
    expect(result.current.isVisible).toBe(false);

    // Clear suppression while still streaming — label should return to "new"
    rerender({ isJumpSuppressed: false, isStreaming: true });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current.isVisible).toBe(true);
    expect(result.current.label).toBe("new");
  });
});
