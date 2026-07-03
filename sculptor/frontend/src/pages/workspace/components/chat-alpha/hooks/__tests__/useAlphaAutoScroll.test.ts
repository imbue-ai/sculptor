import type { Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatMessageRole } from "~/api";

import { PIN_BOTTOM_GAP } from "../../scroll/geometry.ts";
import { useAlphaAutoScroll } from "../useAlphaAutoScroll.ts";

// Mock ResizeObserver — jsdom doesn't provide one.
// We capture callbacks so tests can trigger them to simulate content growth.
// Multiple observers can be active simultaneously.
const resizeObserverCallbacks = new Set<ResizeObserverCallback>();

class MockResizeObserver {
  private callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    resizeObserverCallbacks.add(callback);
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn().mockImplementation(() => {
    resizeObserverCallbacks.delete(this.callback);
  });
}

const createMockScrollContainer = (scrollTop: number, scrollHeight: number, clientHeight: number): HTMLDivElement => {
  const el = document.createElement("div");
  // Add a child to act as firstElementChild (the virtualContent div)
  el.appendChild(document.createElement("div"));
  Object.defineProperty(el, "scrollTop", { value: scrollTop, writable: true, configurable: true });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: clientHeight, writable: true, configurable: true });
  return el;
};

const setScrollPosition = (el: HTMLDivElement, scrollTop: number, scrollHeight: number): void => {
  Object.defineProperty(el, "scrollTop", { value: scrollTop, writable: true, configurable: true });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
};

const createMockVirtualizer = (): Virtualizer<HTMLDivElement, Element> => {
  return {
    scrollToIndex: vi.fn(),
    // The reflow observer and reading-anchor capture read these; empty defaults
    // mean captureReadingAnchor is a no-op (no items) for tests that drive
    // geometry purely through the mock container.
    getVirtualItems: vi.fn(() => []),
    getTotalSize: vi.fn(() => 0),
    measurementsCache: [],
    // paddingEnd: 0 keeps distanceFromContentBottom == scrollHeight-based distance
    // for the tests that drive geometry purely through the mock container.
    options: { paddingEnd: 0 },
  } as unknown as Virtualizer<HTMLDivElement, Element>;
};

/** Simulate a content resize (e.g. streaming text added). */
const triggerResize = (): void => {
  for (const callback of resizeObserverCallbacks) {
    callback([], {} as ResizeObserver);
  }
};

/**
 * Assert the container is pinned to the bottom — scrollTop at bottomPinOffset
 * (content bottom plus the visible PIN_BOTTOM_GAP, clamped to the scroll
 * range; 0 while the content still fits the viewport), the observable position
 * rather than a virtualizer mock call.
 */
const expectPinnedToBottom = (el: HTMLDivElement, paddingEnd = 0): void => {
  const contentBottom = Math.max(0, el.scrollHeight - paddingEnd - el.clientHeight);
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
  expect(el.scrollTop).toBe(contentBottom === 0 ? 0 : Math.min(contentBottom + PIN_BOTTOM_GAP, maxScroll));
};

describe("useAlphaAutoScroll", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", MockResizeObserver);
    resizeObserverCallbacks.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts disengaged", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, false, 10, virtualizer, null, -1, "test-task"));

    expect(result.current.isEngaged).toBe(false);
  });

  it("reports isAtBottom as true initially (no scroll state)", () => {
    // When content fits in the viewport (no scrollbar), isAtBottom should be true
    // so that the "Jump to bottom" / "New activity" button does not appear.
    const el = createMockScrollContainer(0, 500, 500); // no overflow
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, false, 5, virtualizer, null, -1, "test-task"));

    expect(result.current.isAtBottom).toBe(true);
  });

  it("reports isAtBottom when within 200px of bottom", () => {
    // scrollHeight=2000, clientHeight=500, scrollTop=1300 => distance = 200, at bottom
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, false, 10, virtualizer, null, -1, "test-task"));

    act(() => {
      el.dispatchEvent(new Event("scroll"));
    });

    expect(result.current.isAtBottom).toBe(true);
  });

  it("engages when at bottom and streaming starts (via effect, no scroll needed)", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged automatically by the isStreaming effect (at bottom)
    expect(result.current.isEngaged).toBe(true);
  });

  it("does not engage when at bottom but not streaming", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, false, 10, virtualizer, null, -1, "test-task"));

    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });

    expect(result.current.isEngaged).toBe(false);
  });

  it("disengages when user scrolls away from bottom", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged via isStreaming effect
    expect(result.current.isEngaged).toBe(true);

    // User scrolls away (distance > 200)
    setScrollPosition(el, 500, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });

    expect(result.current.isEngaged).toBe(false);
  });

  it("does NOT re-engage when user scrolls back near bottom during streaming", () => {
    // Scrolling near the bottom should not automatically re-engage auto-scroll.
    // Re-engagement only happens via explicit actions (scrollToBottom / jump button)
    // or when a new streaming turn starts. This prevents the view from jumping
    // when the user makes small scroll adjustments.
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engage (from isStreaming effect, since we're at bottom)
    expect(result.current.isEngaged).toBe(true);

    // User scrolls away
    setScrollPosition(el, 500, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);

    // User scrolls back near bottom — should NOT re-engage
    setScrollPosition(el, 1350, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);
  });

  it("ignores non-user scroll events (TanStack correction guard)", () => {
    vi.useFakeTimers();
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged via isStreaming effect
    expect(result.current.isEngaged).toBe(true);

    // User scrolls away — disengages
    setScrollPosition(el, 500, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);

    // Advance past the user-scroll debounce so isUserScrollingRef clears
    act(() => {
      vi.advanceTimersByTime(200);
    });

    // TanStack correction fires a scroll event back to bottom (no wheel event)
    setScrollPosition(el, 1350, 2000);
    act(() => {
      el.dispatchEvent(new Event("scroll"));
    });
    // Should NOT re-engage — no user input signal
    expect(result.current.isEngaged).toBe(false);

    vi.useRealTimers();
  });

  it("disengages when streaming stops", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result, rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: true } },
    );

    // Engaged via isStreaming effect
    expect(result.current.isEngaged).toBe(true);

    // Stop streaming
    rerender({ isStreaming: false });
    expect(result.current.isEngaged).toBe(false);
  });

  it("scrollToBottom works and re-engages during streaming", () => {
    const el = createMockScrollContainer(500, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    act(() => {
      result.current.scrollToBottom();
    });

    expectPinnedToBottom(el);
    expect(result.current.isEngaged).toBe(true);
  });

  it("scrollToBottom does not engage when not streaming", () => {
    const el = createMockScrollContainer(500, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, false, 10, virtualizer, null, -1, "test-task"));

    act(() => {
      result.current.scrollToBottom();
    });

    expectPinnedToBottom(el);
    expect(result.current.isEngaged).toBe(false);
  });

  it("suppressAutoScroll prevents engage/disengage", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    // Start not streaming, enable suppress, then start streaming
    const { result, rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: false } },
    );

    // Enable suppress before streaming starts
    act(() => {
      result.current.setIsSuppressed(true);
    });

    // Start streaming — should NOT engage because suppressed
    rerender({ isStreaming: true });
    expect(result.current.isEngaged).toBe(false);

    // User scroll at bottom while streaming + suppressed — should still NOT engage
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);
  });

  it("auto-engages when streaming starts while already at bottom (no scroll event needed)", () => {
    // User is sitting at the bottom, then streaming starts — auto-scroll should engage
    // without requiring a scroll event (Bug: requirement 1.1)
    const el = createMockScrollContainer(1300, 2000, 500); // distance=200, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    // Start with not streaming, user is at bottom
    const { result, rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: false } },
    );

    // Establish isAtBottom via a scroll event first
    act(() => {
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isAtBottom).toBe(true);
    expect(result.current.isEngaged).toBe(false);

    // Now streaming starts — auto-scroll should engage automatically
    rerender({ isStreaming: true });
    expect(result.current.isEngaged).toBe(true);
  });

  it("auto-engages when new message grew content slightly before streaming starts", () => {
    // User was at bottom, sent a message which grew scrollHeight, pushing them
    // slightly above the old bottom. The streaming-start effect should read the
    // live scroll position (still within threshold) and engage.
    // Desktop-height container (>= 700px), where the at-bottom threshold is 200px.
    const el = createMockScrollContainer(1200, 2000, 800); // distance=0, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result, rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: false } },
    );

    // User was pinned to bottom (distance=0). New message adds ~100px to
    // scrollHeight, pushing distance to 100 — still within the 200px threshold.
    // No scroll event fires, so isAtBottom state reflects the initial value.
    setScrollPosition(el, 1200, 2100); // distance = 2100 - 1200 - 800 = 100 ≤ 200

    // No scroll event fired — isAtBottom state reflects initial value, not live position
    expect(result.current.isAtBottom).toBe(true);

    // Streaming starts — should read live position and engage
    rerender({ isStreaming: true });
    expect(result.current.isEngaged).toBe(true);
  });

  it("does not auto-engage at streaming start 100px above the bottom on a short viewport", () => {
    // Same scenario as above, but the scroll container is short (< 700px), so
    // the at-bottom threshold tightens to 80px (BE2): 100px above the bottom is
    // NOT "at bottom" on mobile, and streaming must not yank the view down.
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result, rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: false } },
    );

    // Content grew by 100px with no scroll event — the same growth the desktop
    // test treats as still-at-bottom (100 ≤ 200).
    setScrollPosition(el, 1500, 2100); // distance = 2100 - 1500 - 500 = 100 > 80

    rerender({ isStreaming: true });
    expect(result.current.isEngaged).toBe(false);
  });

  it("scrolls to bottom when messageCount increases while at bottom (pin-to-bottom)", () => {
    // User is pinned to the bottom (distance=0), not streaming.
    // A new message arrives: messageCount increases and scrollHeight grows by 300px,
    // pushing the user to distance=300 (beyond the 200px threshold).
    // The hook should immediately scroll to the new bottom so the user sees the
    // new message + status pill, without waiting for streaming to start.
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { rerender } = renderHook(
      ({ messageCount }) => useAlphaAutoScroll(ref, false, messageCount, virtualizer, null, -1, "test-task"),
      {
        initialProps: { messageCount: 10 },
      },
    );

    // Establish isAtBottom via scroll event
    act(() => {
      el.dispatchEvent(new Event("scroll"));
    });

    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // New user message added: scrollHeight grows, messageCount increases
    setScrollPosition(el, 1500, 2300); // distance = 2300 - 1500 - 500 = 300 > threshold
    rerender({ messageCount: 11 });

    // Should scroll to show the new message (pinned to the content bottom: 2300 - 500)
    expectPinnedToBottom(el);
  });

  it("does NOT pin-to-bottom when user is scrolled away", () => {
    // User is scrolled away from bottom. A new message arrives but the view
    // should NOT auto-scroll — the user is reading history.
    const el = createMockScrollContainer(200, 2000, 500); // distance=1300, far from bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { rerender } = renderHook(
      ({ messageCount }) => useAlphaAutoScroll(ref, false, messageCount, virtualizer, null, -1, "test-task"),
      {
        initialProps: { messageCount: 10 },
      },
    );

    // Establish NOT at bottom
    act(() => {
      el.dispatchEvent(new Event("scroll"));
    });

    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // New message arrives
    setScrollPosition(el, 200, 2300);
    rerender({ messageCount: 11 });

    // Should NOT scroll — user is reading history
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("disengages on any user scroll while engaged, even if still near bottom", () => {
    // A tiny scroll (still within BOTTOM_THRESHOLD) during streaming should
    // disengage auto-scroll.
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Auto-engaged via streaming-start effect (at bottom)
    expect(result.current.isEngaged).toBe(true);

    // User scrolls up just a tiny bit — still within 200px threshold (distance=50)
    setScrollPosition(el, 1450, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });

    // Should disengage even though still near bottom
    expect(result.current.isEngaged).toBe(false);
  });

  it("does not re-engage via ResizeObserver after user scroll disengages", () => {
    // After disengaging with a tiny scroll, content growth should NOT
    // pull the user back to the bottom.
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    expect(result.current.isEngaged).toBe(true);

    // Tiny user scroll
    setScrollPosition(el, 1450, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);

    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // Content grows (streaming) — should NOT scroll to bottom
    act(() => {
      triggerResize();
    });
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("updates isAtBottom when content grows during streaming (no scroll needed)", () => {
    // After user disengages with a tiny scroll, they're still near the bottom.
    // As streaming adds content, the bottom moves away. isAtBottom should update
    // via ResizeObserver so the "jump to bottom" button appears without needing
    // a scroll event.
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged via isStreaming effect
    expect(result.current.isEngaged).toBe(true);
    expect(result.current.isAtBottom).toBe(true);

    // User scrolls up a tiny bit → disengages
    setScrollPosition(el, 1450, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);
    // Still near bottom (distance=50)
    expect(result.current.isAtBottom).toBe(true);

    // Streaming adds lots of content — bottom moves far away
    // scrollTop stays at 1450, scrollHeight grows to 2500 → distance = 2500-1450-500 = 550
    setScrollPosition(el, 1450, 2500);
    act(() => {
      triggerResize();
    });

    // isAtBottom should now be false — button should appear
    expect(result.current.isAtBottom).toBe(false);
  });

  it("ResizeObserver scrolls to bottom when content grows while engaged", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged via isStreaming effect (at bottom)
    expect(result.current.isEngaged).toBe(true);

    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // Simulate content growing (streaming adds text) so the content bottom drifts
    // below the viewport, then a resize fires.
    setScrollPosition(el, 1500, 2500); // grew; distance = 2500 - 1500 - 500 = 500
    act(() => {
      triggerResize();
    });

    // The resize re-pins to the new content bottom (2500 - 500).
    expectPinnedToBottom(el);
  });

  it("ResizeObserver disconnects when disengaged", () => {
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged via isStreaming effect
    expect(result.current.isEngaged).toBe(true);

    // User scrolls away — disengages, which should disconnect the observer
    setScrollPosition(el, 500, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);

    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // Content resize should NOT cause scroll (observer disconnected)
    act(() => {
      triggerResize();
    });

    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("re-engages when user scrolls to exact bottom during streaming", () => {
    // After disengaging, if the user scrolls all the way to the bottom
    // (distance ≈ 0), auto-scroll should re-engage — this is an intentional
    // gesture to resume following the stream.
    const el = createMockScrollContainer(1300, 2000, 500); // distance=200, at bottom
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

    // Engaged via isStreaming effect
    expect(result.current.isEngaged).toBe(true);

    // User scrolls away → disengage
    setScrollPosition(el, 500, 2000);
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });
    expect(result.current.isEngaged).toBe(false);

    // User scrolls to the very bottom (distance=0)
    setScrollPosition(el, 1500, 2000); // distance = 2000 - 1500 - 500 = 0
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });

    // Should re-engage
    expect(result.current.isEngaged).toBe(true);
  });

  it("does NOT re-engage at exact bottom when not streaming", () => {
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useAlphaAutoScroll(ref, false, 10, virtualizer, null, -1, "test-task"));

    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });

    expect(result.current.isEngaged).toBe(false);
  });

  it("does NOT re-engage at exact bottom when suppressed", () => {
    const el = createMockScrollContainer(1500, 2000, 500); // distance=0
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    // Start not streaming, then suppress, then start streaming — won't engage
    const { result, rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: false } },
    );

    act(() => {
      result.current.setIsSuppressed(true);
    });

    rerender({ isStreaming: true });
    expect(result.current.isEngaged).toBe(false);

    // Scroll to exact bottom while suppressed + streaming
    setScrollPosition(el, 1500, 2000); // distance=0
    act(() => {
      el.dispatchEvent(new Event("wheel"));
      el.dispatchEvent(new Event("scroll"));
    });

    // Should NOT re-engage (suppressed)
    expect(result.current.isEngaged).toBe(false);
  });

  describe("scroll-to-top on send", () => {
    const createMockVirtualizerWithFilling = (
      totalSize: number,
      paddingEnd: number,
    ): Virtualizer<HTMLDivElement, Element> => {
      return {
        scrollToIndex: vi.fn(),
        getTotalSize: vi.fn().mockReturnValue(totalSize),
        getVirtualItems: vi.fn(() => []),
        options: { paddingEnd },
        measurementsCache: [] as Array<unknown>,
      } as unknown as Virtualizer<HTMLDivElement, Element>;
    };

    it("fires on new user message", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, lastUserMessageIndex }) =>
          useAlphaAutoScroll(ref, false, messageCount, virtualizer, lastMessageRole, lastUserMessageIndex, "test-task"),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
          },
        },
      );

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // New user message arrives
      rerender({ messageCount: 11, lastMessageRole: ChatMessageRole.USER, lastUserMessageIndex: 10 });

      expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(10, { align: "start" });
      expect(result.current.isEngaged).toBe(true);
      expect(result.current.isJumpSuppressed).toBe(true);
    });

    it("does NOT fire on new assistant message", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { rerender } = renderHook(
        ({ messageCount, lastMessageRole, lastUserMessageIndex }) =>
          useAlphaAutoScroll(ref, false, messageCount, virtualizer, lastMessageRole, lastUserMessageIndex, "test-task"),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
          },
        },
      );

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // New assistant message arrives
      rerender({ messageCount: 11, lastMessageRole: ChatMessageRole.ASSISTANT, lastUserMessageIndex: -1 });

      // scrollToIndex may be called for pin-to-bottom, but NOT with align: "start"
      const startCalls = vi
        .mocked(virtualizer.scrollToIndex)
        .mock.calls.filter((call) => (call[1] as { align: string })?.align === "start");
      expect(startCalls).toHaveLength(0);
    });

    it("does NOT fire when suppressed", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, lastUserMessageIndex }) =>
          useAlphaAutoScroll(ref, false, messageCount, virtualizer, lastMessageRole, lastUserMessageIndex, "test-task"),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
          },
        },
      );

      // Suppress auto-scroll
      act(() => {
        result.current.setIsSuppressed(true);
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // New user message arrives while suppressed
      rerender({ messageCount: 11, lastMessageRole: ChatMessageRole.USER, lastUserMessageIndex: 10 });

      // scrollToIndex should NOT be called with align: "start"
      const startCalls = vi
        .mocked(virtualizer.scrollToIndex)
        .mock.calls.filter((call) => (call[1] as { align: string })?.align === "start");
      expect(startCalls).toHaveLength(0);
    });

    it("pin-to-bottom skips user messages", () => {
      // Pin-to-bottom should NOT fire when the last message is a user message,
      // because scroll-to-top handles that case instead.
      const el = createMockScrollContainer(1500, 2000, 500); // distance=0, at bottom
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { rerender } = renderHook(
        ({ messageCount, lastMessageRole, lastUserMessageIndex }) =>
          useAlphaAutoScroll(ref, false, messageCount, virtualizer, lastMessageRole, lastUserMessageIndex, "test-task"),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
          },
        },
      );

      // Establish isAtBottom
      act(() => {
        el.dispatchEvent(new Event("scroll"));
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // New user message arrives while at bottom
      rerender({ messageCount: 11, lastMessageRole: ChatMessageRole.USER, lastUserMessageIndex: 10 });

      // scrollToIndex with align: "end" should NOT be called (pin-to-bottom
      // defers to scroll-to-top for user messages)
      const endCalls = vi
        .mocked(virtualizer.scrollToIndex)
        .mock.calls.filter((call) => (call[1] as { align: string })?.align === "end");
      expect(endCalls).toHaveLength(0);
    });

    it("isJumpSuppressed stays true during filling and clears when filling ends", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message — isJumpSuppressed becomes true, filling starts
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isJumpSuppressed).toBe(true);

      // Streaming starts — isJumpSuppressed should STAY true during filling
      // (the button would incorrectly appear because isAtBottom is false
      // during filling to prevent pin-to-bottom from overriding scroll-to-top)
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });
      expect(result.current.isJumpSuppressed).toBe(true);
    });

    it("filling phase exits on user scroll", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message to enter filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      // The scroll-to-top effect sets isProgrammaticScrollRef. Consume it
      // with a bare scroll event so it doesn't swallow the real user scroll.
      act(() => {
        el.dispatchEvent(new Event("scroll"));
      });

      // Start streaming so the resize observer is set up
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // User scrolls away — should exit filling phase and disengage.
      setScrollPosition(el, 800, 2000);
      act(() => {
        el.dispatchEvent(new Event("wheel"));
        el.dispatchEvent(new Event("scroll"));
      });

      // The user scroll disengages auto-scroll entirely
      expect(result.current.isEngaged).toBe(false);

      // Trigger a resize — should NOT call scrollToIndex (disengaged)
      vi.mocked(virtualizer.scrollToIndex).mockClear();
      act(() => {
        triggerResize();
      });
      expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    });

    it("isAtBottom is true after streaming ends in filling phase (short response — jump button must not appear)", () => {
      // When streaming ends while still in filling phase the response was short
      // enough to fit in the viewport without overflowing.  The virtualizer's
      // large paddingEnd inflates scrollHeight so a live distance check would
      // return false, incorrectly showing the jump-to-bottom button.
      // isAtBottom must be set to true unconditionally in this case.
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send user message — filling phase, isAtBottom forced to false
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isAtBottom).toBe(false);

      // Short response streams in (no overflow)
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.ASSISTANT,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      // Streaming ends while still in filling phase
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.ASSISTANT,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });

      // isAtBottom must be true — content fit in viewport, nothing to scroll to.
      // Jump button must NOT appear.
      expect(result.current.isAtBottom).toBe(true);
      expect(result.current.isJumpSuppressed).toBe(false);
    });

    it("filling phase exits on streaming end", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message — enters filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      // Start streaming while in filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });
      expect(result.current.isEngaged).toBe(true);

      // Stop streaming — filling phase should clear and auto-scroll disengages
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(false);
    });

    it("refreshes isAtBottom from live scroll position when filling ends on streaming stop", () => {
      // Regression: for a short non-streaming response, the streaming-end
      // cleanup clears isJumpSuppressed but the final scrollToIndex may be a
      // no-op (scrollTop unchanged), so no scroll event fires and isAtBottom
      // stays stale `false` from the filling phase.  That stale state makes
      // the jump-to-bottom button appear 150ms later via useJumpToBottom's
      // debounce even though the viewport is at the bottom.
      //
      // Mock the viewport at the bottom (distance=50) before streaming ends,
      // and verify isAtBottom updates to `true` so consumers see the correct
      // state without needing a scroll event.
      const el = createMockScrollContainer(50, 550, 500); // distance=50, near bottom
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(550, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message — enters filling phase, scroll-to-top forces
      // isAtBottom to false so pin-to-bottom can't override.
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isJumpSuppressed).toBe(true);
      expect(result.current.isAtBottom).toBe(false);

      // Brief streaming, then response completes.
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });

      // Suppression cleared AND isAtBottom refreshed from live DOM.
      expect(result.current.isJumpSuppressed).toBe(false);
      expect(result.current.isAtBottom).toBe(true);
    });

    it("scrollToBottom clears filling phase", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message — enters filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      // Start streaming
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Anchoring places the user message near the top; start from a realistic
      // scrolled-up position rather than parked in the empty tail padding.
      setScrollPosition(el, 500, 2000);

      // Call scrollToBottom — should clear filling phase and pin to the content
      // bottom (scrollHeight 2000 - paddingEnd 100 - clientHeight 500 = 1400).
      act(() => {
        result.current.scrollToBottom();
      });

      expectPinnedToBottom(el, 100);

      // Drift up, then a resize should re-pin to the content bottom (following),
      // not hold the position (filling/holdTurn) — confirming filling was cleared.
      setScrollPosition(el, 1000, 2000);
      act(() => {
        triggerResize();
      });
      expectPinnedToBottom(el, 100);
    });

    it("isAtBottom tracks via ResizeObserver even when not engaged during streaming", () => {
      // Start streaming but NOT engaged (far from bottom).
      // The merged observer should still track isAtBottom regardless of engagement.
      const el = createMockScrollContainer(200, 2000, 500); // distance=1200, far from bottom
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      // lastMessageRole=USER so the on-mount pin-to-bottom bails (it only pins for
      // non-user messages), keeping this test's scrolled-up, not-engaged premise.
      const { result } = renderHook(() =>
        useAlphaAutoScroll(ref, true, 10, virtualizer, ChatMessageRole.USER, -1, "test-task"),
      );

      // Not engaged because too far from bottom when streaming started
      expect(result.current.isEngaged).toBe(false);

      // Trigger a resize while scroll position shows distance > 200
      act(() => {
        triggerResize();
      });
      expect(result.current.isAtBottom).toBe(false);

      // Change scroll position to near bottom, trigger another resize
      setScrollPosition(el, 1350, 2000); // distance = 2000 - 100 - 1350 - 500 = 50 ≤ 200
      act(() => {
        triggerResize();
      });
      expect(result.current.isAtBottom).toBe(true);
    });

    it("merged observer continues tracking isAtBottom after disengage", () => {
      // The merged observer must continue tracking isAtBottom even after
      // disengagement.
      const el = createMockScrollContainer(1500, 2000, 500); // distance=0, at bottom
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result } = renderHook(() => useAlphaAutoScroll(ref, true, 10, virtualizer, null, -1, "test-task"));

      // Engaged via isStreaming effect (at bottom)
      expect(result.current.isEngaged).toBe(true);
      expect(result.current.isAtBottom).toBe(true);

      // User scrolls away → disengages
      setScrollPosition(el, 500, 2000); // distance = 2000 - 500 - 500 = 1000
      act(() => {
        el.dispatchEvent(new Event("wheel"));
        el.dispatchEvent(new Event("scroll"));
      });
      expect(result.current.isEngaged).toBe(false);

      // Content grows (triggerResize) while scroll stays far from bottom
      setScrollPosition(el, 500, 2500); // distance = 2500 - 500 - 500 = 1500
      act(() => {
        triggerResize();
      });

      // Observer is still active — isAtBottom should be false
      expect(result.current.isAtBottom).toBe(false);
    });

    it("filling phase transitions to pin-to-bottom on content overflow", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      // Start with totalSize that doesn't overflow (small content)
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message to enter filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Start streaming with assistant response so the resize observer is set up.
      // messageCount=12 means there's an assistant message after the user (index 11),
      // which is required for the overflow check to trigger pin-to-bottom.
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.ASSISTANT,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Mock getTotalSize to return a value that overflows.
      // The overflow check compares tailHeight (content after the anchor) to clientHeight.
      // Set up the measurementsCache so the anchor item (index 10) has known dimensions.
      const anchorStart = 500;
      const anchorSize = 100;
      (
        virtualizer as unknown as { measurementsCache: Record<number, { start: number; size: number }> }
      ).measurementsCache = {
        10: { start: anchorStart, size: anchorSize },
      };
      const anchorEnd = anchorStart + anchorSize;
      vi.mocked(virtualizer.getTotalSize).mockReturnValue(anchorEnd + el.clientHeight + 200);

      // Anchoring holds the user message near the top; start scrolled up.
      setScrollPosition(el, 500, 2000);

      // Trigger resize — should detect overflow and pin to the content bottom
      // (scrollHeight 2000 - paddingEnd 100 - clientHeight 500 = 1400).
      act(() => {
        triggerResize();
      });
      expectPinnedToBottom(el, 100);

      // Drift up, then another resize should re-pin (following, no longer filling).
      setScrollPosition(el, 1000, 2000);
      act(() => {
        triggerResize();
      });
      expectPinnedToBottom(el, 100);
    });

    it("filling phase overflow accounts for user message height (not full clientHeight)", () => {
      // Bug: overflow was detected when tailHeight >= clientHeight, but the user
      // message already occupies the top of the viewport. Overflow should trigger
      // when tailHeight >= clientHeight - anchorSize (remaining space below user msg).
      const el = createMockScrollContainer(1500, 2000, 500); // clientHeight=500
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.ASSISTANT,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Anchor item: start=500, size=150. anchorEnd=650.
      // Overflow threshold = clientHeight(500) - anchorSize(150) = 350.
      // Set tailHeight = 350 (exactly at threshold) — should transition.
      const anchorStart = 500;
      const anchorSize = 150;
      (
        virtualizer as unknown as { measurementsCache: Record<number, { start: number; size: number }> }
      ).measurementsCache = {
        10: { start: anchorStart, size: anchorSize },
      };
      // tailHeight = contentBottom - anchorEnd = 350 → contentBottom = anchorEnd + 350 = 1000
      // getTotalSize = contentBottom + paddingEnd = 1000 + 100 = 1100
      vi.mocked(virtualizer.getTotalSize).mockReturnValue(1100);

      // Anchoring holds the user message near the top; start scrolled up.
      setScrollPosition(el, 500, 2000);

      act(() => {
        triggerResize();
      });

      // Transitioned to following: pinned to the content bottom (2000 - 100 - 500).
      expectPinnedToBottom(el, 100);
    });

    it("does NOT scroll at streaming end when still in filling phase (short response)", () => {
      // Bug: the isStreaming effect called scrollToIndex(last, "end") at streaming end
      // even during filling phase. With inflated paddingEnd, this landed near
      // scrollTop=0, producing a visible "scroll to top" just before the turn footer.
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send user message → filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });

      // Start streaming with short response (messageCount 12, but no overflow)
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.ASSISTANT,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Streaming ends while still in filling phase (response was short, never overflowed)
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.ASSISTANT,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });

      // At streaming end while still anchoring a short response, the view must stay
      // put: the down-only content-bottom pin leaves scrollTop where it was rather
      // than jumping toward the top.
      expect(el.scrollTop).toBe(1500);
    });

    it("second user message during filling cancels previous and re-enters filling", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send first user message → enters filling, engaged
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Send second user message (increment messageCount again, lastMessageRole=USER)
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 11,
        isStreaming: false,
      });

      // Should scroll to new message index with align: "start"
      expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(11, { align: "start" });
      // Should still be engaged (re-engaged by second scroll-to-top)
      expect(result.current.isEngaged).toBe(true);
    });

    it("suppression during filling phase prevents scroll-to-top", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizerWithFilling(300, 100);

      const { result, rerender } = renderHook(
        ({ messageCount, lastMessageRole, isStreaming, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            lastMessageRole,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastMessageRole: null as ChatMessageRole | null,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send first user message to enter filling phase
      rerender({
        messageCount: 11,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      // Set suppressed = true
      act(() => {
        result.current.setIsSuppressed(true);
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Send another user message while suppressed
      rerender({
        messageCount: 12,
        lastMessageRole: ChatMessageRole.USER,
        lastUserMessageIndex: 11,
        isStreaming: false,
      });

      // scrollToIndex should NOT be called with align: "start" for the second message
      const startCalls = vi
        .mocked(virtualizer.scrollToIndex)
        .mock.calls.filter((call) => (call[1] as { align: string })?.align === "start");
      expect(startCalls).toHaveLength(0);
    });
  });

  it("scroll-to-top updates paddingEnd and content height when virtualizer padding is stale", () => {
    // Bug: when a new user message is sent after a long assistant response,
    // the virtualizer's paddingEnd is based on stale tailContentHeight state
    // from the previous render. This causes scrollToIndex to be clamped by
    // the browser's scrollHeight, and the message ends up mid-viewport.
    //
    // The fix should update virtualizer.options.paddingEnd and the DOM
    // content element's height BEFORE calling scrollToIndex.
    const el = createMockScrollContainer(2600, 3200, 700);
    const ref = { current: el };

    let paddingEndAtScrollTime: number | undefined;

    const virtualizerObj: {
      scrollToIndex: (index: number, options: { align: string }) => void;
      options: { paddingEnd: number };
      measurementsCache: ReadonlyArray<{ start: number; size: number }>;
      getTotalSize: () => number;
      shouldAdjustScrollPositionOnItemSizeChange: unknown;
    } = {
      scrollToIndex: vi.fn().mockImplementation(() => {
        // Capture paddingEnd at the moment scrollToIndex is called
        paddingEndAtScrollTime = virtualizerObj.options.paddingEnd;
      }),
      options: { paddingEnd: 128 }, // Stale — based on old tailContentHeight
      measurementsCache: [
        { start: 128, size: 80 }, // item 0: first user message
        { start: 208, size: 2800 }, // item 1: long assistant response
        { start: 3008, size: 60 }, // item 2: new user message (scroll-to-top target)
      ],
      getTotalSize: vi.fn(() => 128 + 80 + 2800 + 60 + virtualizerObj.options.paddingEnd),
      shouldAdjustScrollPositionOnItemSizeChange: null,
    };
    const virtualizer = virtualizerObj as unknown as Virtualizer<HTMLDivElement, Element>;

    // Initial render: 2 messages, last user message at index 0
    const { rerender } = renderHook(
      ({
        messageCount,
        lastUserIdx,
        lastRole,
      }: {
        messageCount: number;
        lastUserIdx: number;
        lastRole: ChatMessageRole | null;
      }) => useAlphaAutoScroll(ref, false, messageCount, virtualizer, lastRole, lastUserIdx, "test-task"),
      {
        initialProps: {
          messageCount: 2,
          lastUserIdx: 0,
          lastRole: ChatMessageRole.ASSISTANT as ChatMessageRole | null,
        },
      },
    );

    vi.mocked(virtualizer.scrollToIndex).mockClear();
    paddingEndAtScrollTime = undefined;

    // New user message arrives: messageCount and lastUserMessageIndex increase
    rerender({
      messageCount: 3,
      lastUserIdx: 2,
      lastRole: ChatMessageRole.USER,
    });

    // Scroll-to-top should have fired
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(2, { align: "start" });

    // The fix: paddingEnd must be updated BEFORE scrollToIndex is called.
    // Without the fix, paddingEnd stays at 128 (stale), so the browser clamps
    // scrollTop and the user message appears mid-viewport instead of at the top.
    // Required paddingEnd = clientHeight(700) - itemSize(60) = 640
    expect(paddingEndAtScrollTime).toBeGreaterThanOrEqual(640);

    // Content element height should also have been updated
    const contentEl = el.firstElementChild as HTMLElement;
    expect(contentEl.style.height).not.toBe("");
  });

  describe("task switch resets scroll state", () => {
    it("resets isAtBottom, isEngaged, and isJumpSuppressed on task switch", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizer();

      const { result, rerender } = renderHook(
        ({ taskId, isStreaming, messageCount, lastUserMessageIndex }) =>
          useAlphaAutoScroll(ref, isStreaming, messageCount, virtualizer, null, lastUserMessageIndex, taskId),
        {
          initialProps: {
            taskId: "task-a",
            isStreaming: true,
            messageCount: 10,
            lastUserMessageIndex: -1,
          },
        },
      );

      // Establish engaged + at bottom on task A
      expect(result.current.isEngaged).toBe(true);

      // Switch to task B
      rerender({
        taskId: "task-b",
        isStreaming: false,
        messageCount: 5,
        lastUserMessageIndex: -1,
      });

      // Should NOT carry over isEngaged from task A
      expect(result.current.isEngaged).toBe(false);
    });

    it("does not trigger scroll-to-top on task switch when lastUserMessageIndex stays the same", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = createMockVirtualizer();

      const { rerender } = renderHook(
        ({ taskId, messageCount, lastUserMessageIndex }) =>
          useAlphaAutoScroll(ref, false, messageCount, virtualizer, ChatMessageRole.USER, lastUserMessageIndex, taskId),
        {
          initialProps: {
            taskId: "task-a",
            messageCount: 5,
            lastUserMessageIndex: 4,
          },
        },
      );

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Switch to task B with same lastUserMessageIndex (different task, same index)
      rerender({
        taskId: "task-b",
        messageCount: 5,
        lastUserMessageIndex: 4,
      });

      // scrollToIndex should NOT be called with align: "start" — the task switch
      // resets prevLastUserMessageIndexRef so index 4 is not "new"
      const startCalls = vi
        .mocked(virtualizer.scrollToIndex)
        .mock.calls.filter((call) => (call[1] as { align: string })?.align === "start");
      expect(startCalls).toHaveLength(0);
    });

    it("does not trigger spurious pin-to-bottom on task switch", () => {
      const el = createMockScrollContainer(1500, 2000, 500); // distance=0
      const ref = { current: el };
      const virtualizer = createMockVirtualizer();

      const { rerender } = renderHook(
        ({ taskId, messageCount }) =>
          useAlphaAutoScroll(ref, false, messageCount, virtualizer, ChatMessageRole.ASSISTANT, -1, taskId),
        {
          initialProps: {
            taskId: "task-a",
            messageCount: 10,
          },
        },
      );

      // Establish at bottom on task A
      act(() => {
        el.dispatchEvent(new Event("scroll"));
      });

      vi.mocked(virtualizer.scrollToIndex).mockClear();

      // Switch to task B — the reset clears isAtBottomRef, so pin-to-bottom
      // should NOT fire even though the previous isAtBottom state was true
      rerender({
        taskId: "task-b",
        messageCount: 3,
      });

      const endCalls = vi
        .mocked(virtualizer.scrollToIndex)
        .mock.calls.filter((call) => (call[1] as { align: string })?.align === "end");
      expect(endCalls).toHaveLength(0);
    });
  });

  describe("filling phase isAtBottom guard", () => {
    it("does NOT mark as at-bottom during filling phase when near bottom", () => {
      const el = createMockScrollContainer(1500, 2000, 500); // distance=0
      const ref = { current: el };
      const virtualizer = {
        scrollToIndex: vi.fn(),
        getTotalSize: vi.fn().mockReturnValue(300),
        options: { paddingEnd: 100 },
        measurementsCache: [] as Array<unknown>,
      } as unknown as Virtualizer<HTMLDivElement, Element>;

      const { result, rerender } = renderHook(
        ({ messageCount, lastUserMessageIndex, isStreaming }) =>
          useAlphaAutoScroll(
            ref,
            isStreaming,
            messageCount,
            virtualizer,
            ChatMessageRole.USER,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastUserMessageIndex: -1,
            isStreaming: false,
          },
        },
      );

      // Send a user message to enter filling phase
      rerender({
        messageCount: 11,
        lastUserMessageIndex: 10,
        isStreaming: false,
      });
      expect(result.current.isEngaged).toBe(true);

      // Start streaming
      rerender({
        messageCount: 11,
        lastUserMessageIndex: 10,
        isStreaming: true,
      });

      // Virtualizer correction temporarily shrinks scrollHeight so distance ≈ 0.
      // During filling, this should NOT mark isAtBottom = true.
      setScrollPosition(el, 1500, 2000); // distance = 0
      act(() => {
        triggerResize();
      });

      // isAtBottom should still be false during filling to prevent pin-to-bottom
      expect(result.current.isAtBottom).toBe(false);
    });

    it("marks as not-at-bottom during filling even via scroll event", () => {
      const el = createMockScrollContainer(1500, 2000, 500);
      const ref = { current: el };
      const virtualizer = {
        scrollToIndex: vi.fn(),
        getTotalSize: vi.fn().mockReturnValue(300),
        options: { paddingEnd: 100 },
        measurementsCache: [] as Array<unknown>,
      } as unknown as Virtualizer<HTMLDivElement, Element>;

      const { result, rerender } = renderHook(
        ({ messageCount, lastUserMessageIndex }) =>
          useAlphaAutoScroll(
            ref,
            false,
            messageCount,
            virtualizer,
            ChatMessageRole.USER,
            lastUserMessageIndex,
            "test-task",
          ),
        {
          initialProps: {
            messageCount: 10,
            lastUserMessageIndex: -1,
          },
        },
      );

      // Enter filling phase
      rerender({
        messageCount: 11,
        lastUserMessageIndex: 10,
      });

      // Scroll event at near-bottom during filling should NOT update isAtBottom to true
      setScrollPosition(el, 1500, 2000); // distance = 0
      act(() => {
        el.dispatchEvent(new Event("scroll"));
      });

      expect(result.current.isAtBottom).toBe(false);
    });
  });

  it("scrollToBottom clears isJumpSuppressed", () => {
    const el = createMockScrollContainer(1500, 2000, 500);
    const ref = { current: el };
    const virtualizer = {
      scrollToIndex: vi.fn(),
      getTotalSize: vi.fn().mockReturnValue(300),
      options: { paddingEnd: 100 },
      measurementsCache: [] as Array<unknown>,
    } as unknown as Virtualizer<HTMLDivElement, Element>;

    const { result, rerender } = renderHook(
      ({ messageCount, lastUserMessageIndex, isStreaming }) =>
        useAlphaAutoScroll(
          ref,
          isStreaming,
          messageCount,
          virtualizer,
          ChatMessageRole.USER,
          lastUserMessageIndex,
          "test-task",
        ),
      {
        initialProps: {
          messageCount: 10,
          lastUserMessageIndex: -1,
          isStreaming: false,
        },
      },
    );

    // Enter filling phase (which sets isJumpSuppressed)
    rerender({
      messageCount: 11,
      lastUserMessageIndex: 10,
      isStreaming: false,
    });
    expect(result.current.isJumpSuppressed).toBe(true);

    // Start streaming
    rerender({
      messageCount: 11,
      lastUserMessageIndex: 10,
      isStreaming: true,
    });

    // Call scrollToBottom — should clear isJumpSuppressed
    act(() => {
      result.current.scrollToBottom();
    });

    expect(result.current.isJumpSuppressed).toBe(false);
  });

  it("first user message (index 0) does not scroll but enters filling phase", () => {
    // The scroll-to-top animation is skipped so the chat intro stays visible,
    // but filling phase is entered so that auto-scroll can engage via the
    // ResizeObserver overflow check instead of the broken distance-check path
    // (which fails for index 0 because the large paddingEnd inflates distance
    // beyond BOTTOM_THRESHOLD before any response content arrives).
    const el = createMockScrollContainer(500, 1000, 500);
    const ref = { current: el };
    const virtualizer = {
      scrollToIndex: vi.fn(),
      getTotalSize: vi.fn().mockReturnValue(600),
      options: { paddingEnd: 100 },
      measurementsCache: [] as Array<unknown>,
      shouldAdjustScrollPositionOnItemSizeChange: null as unknown,
    } as unknown as Virtualizer<HTMLDivElement, Element>;

    const initialScrollTop = el.scrollTop;

    const { result, rerender } = renderHook(
      ({ messageCount, lastUserMessageIndex }) =>
        useAlphaAutoScroll(
          ref,
          false,
          messageCount,
          virtualizer,
          ChatMessageRole.USER,
          lastUserMessageIndex,
          "test-task",
        ),
      {
        initialProps: {
          messageCount: 0,
          lastUserMessageIndex: -1,
        },
      },
    );

    // First user message at index 0
    rerender({
      messageCount: 1,
      lastUserMessageIndex: 0,
    });

    // No scrollToIndex call — intro must stay visible.
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(el.scrollTop).toBe(initialScrollTop);

    // Filling phase entered: engaged and jump suppressed so pin-to-bottom
    // cannot fire and the jump button does not flash.
    expect(result.current.isEngaged).toBe(true);
    expect(result.current.isJumpSuppressed).toBe(true);
  });

  it("anchor scroll at streaming end is skipped when already at bottom", () => {
    // The ResizeObserver keeps scrollTop at the bottom throughout streaming.
    // Firing scrollToIndex again at streaming end — when paddingEnd may have
    // changed in the same render — causes a visible jump.  The guard
    // liveDistance > 1 prevents this no-op (or harmful) call.
    const el = createMockScrollContainer(1500, 2000, 500); // distance = 0
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: true } },
    );

    // Engaged via isStreaming effect (at bottom)
    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // Streaming stops while already at the very bottom (distance = 0)
    rerender({ isStreaming: false });

    // Anchor scroll should NOT fire — we're already at distance = 0
    const endCalls = vi
      .mocked(virtualizer.scrollToIndex)
      .mock.calls.filter((call) => (call[1] as { align: string })?.align === "end");
    expect(endCalls).toHaveLength(0);
  });

  it("anchor scroll at streaming end fires when drifted from bottom", () => {
    // If the position drifted (e.g. paddingEnd changed mid-render) without a
    // user scroll event — so engagement stays active but distance > 1 — the
    // anchor scroll should re-pin to the bottom.
    const el = createMockScrollContainer(1500, 2000, 500); // start at bottom (distance=0)
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();

    const { rerender } = renderHook(
      ({ isStreaming }) => useAlphaAutoScroll(ref, isStreaming, 10, virtualizer, null, -1, "test-task"),
      { initialProps: { isStreaming: true } },
    );

    // Engaged via isStreaming effect (distance = 0, at bottom)
    // Simulate drift without a scroll event (paddingEnd recalc, etc.)
    setScrollPosition(el, 1000, 2000); // distance = 500 > 1, still engaged (no scroll event)

    vi.mocked(virtualizer.scrollToIndex).mockClear();

    // Streaming stops while drifted — the final settle should re-pin to the
    // content bottom (2000 - 500).
    rerender({ isStreaming: false });

    expectPinnedToBottom(el);
  });
});
