import type { Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import type { RefObject } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createScrollStateMachine, type ScrollStateMachine } from "../../scroll/scrollStateMachine.ts";
import { useActivePromptIndex } from "../useActivePromptIndex.ts";

const SCROLL_THROTTLE_MS = 100;

type MeasurementCacheEntry = { start: number };

const createMockVirtualizer = (
  measurementsCache: ReadonlyArray<MeasurementCacheEntry>,
): Virtualizer<HTMLDivElement, Element> =>
  ({
    measurementsCache,
  }) as unknown as Virtualizer<HTMLDivElement, Element>;

const createScrollContainer = (): HTMLDivElement => {
  const el = document.createElement("div");
  document.body.appendChild(el);
  return el;
};

const setScrollTop = (el: HTMLDivElement, value: number): void => {
  Object.defineProperty(el, "scrollTop", { configurable: true, value });
};

describe("useActivePromptIndex", () => {
  let container: HTMLDivElement;
  let scrollContainerRef: RefObject<HTMLDivElement | null>;
  let machine: ScrollStateMachine;

  beforeEach(() => {
    vi.useFakeTimers();
    container = createScrollContainer();
    setScrollTop(container, 0);
    scrollContainerRef = { current: container };
    machine = createScrollStateMachine();
  });

  afterEach(() => {
    if (container.parentNode) {
      document.body.removeChild(container);
    }
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("returns index 0 when userPromptIndices is empty", () => {
    const virtualizer = createMockVirtualizer([]);

    const { result } = renderHook(() => useActivePromptIndex([], virtualizer, scrollContainerRef, false, machine));

    expect(result.current.index).toBe(0);
  });

  it("computes the correct active index on scroll", () => {
    // 3 prompts at virtual starts 0, 500, 1000 (indices 0, 1, 2 in messages)
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);
    const userPromptIndices = [0, 1, 2];

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, false, machine),
    );

    // On mount, compute() runs with scrollTop=0 -> only start=0 <= 200, so active=0
    expect(result.current.index).toBe(0);

    // Set scrollTop=600 and dispatch a scroll event.
    // start=0 <= 800 ✓, start=500 <= 800 ✓, start=1000 > 800 -> active=1
    act(() => {
      setScrollTop(container, 600);
      container.dispatchEvent(new Event("scroll"));
      // Flush throttle (leading+trailing). Leading fires synchronously; advance time anyway.
      vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    });

    expect(result.current.index).toBe(1);
  });

  it("sticks to last prompt when isAtBottom is true", () => {
    const virtualizer = createMockVirtualizer([
      { start: 0 },
      { start: 100 },
      { start: 200 },
      { start: 300 },
      { start: 400 },
    ]);
    const userPromptIndices = [0, 1, 2, 3, 4];

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, true, machine),
    );

    // Regardless of scroll-computed value, stick-to-bottom wins -> length-1 = 4
    expect(result.current.index).toBe(4);
  });

  it("flicker bridge: holds last-dot while isAtBottom briefly flips false but length does not shrink", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);
    const initialIndices = [0, 1, 2];

    const { result, rerender } = renderHook(
      ({ indices, isAtBottom }) => useActivePromptIndex(indices, virtualizer, scrollContainerRef, isAtBottom, machine),
      { initialProps: { indices: initialIndices as ReadonlyArray<number>, isAtBottom: true } },
    );

    // Initially at bottom -> index = last = 2
    expect(result.current.index).toBe(2);

    // Now isAtBottom flips false, same length -> wasAtBottom && length not shrunk -> still sticks
    rerender({ indices: initialIndices as ReadonlyArray<number>, isAtBottom: false });
    expect(result.current.index).toBe(2);

    // Rerender again with isAtBottom=false, same length.  wasAtBottom (from previous
    // render) is now false, so shouldStickToBottom is false and it falls back to
    // the scroll-computed activeIndex (which is 0 since scrollTop=0).
    rerender({ indices: initialIndices as ReadonlyArray<number>, isAtBottom: false });
    expect(result.current.index).toBe(0);
  });

  it("flicker bridge: does NOT stick when length shrinks", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);

    const { result, rerender } = renderHook(
      ({ indices, isAtBottom }) => useActivePromptIndex(indices, virtualizer, scrollContainerRef, isAtBottom, machine),
      { initialProps: { indices: [0, 1, 2] as ReadonlyArray<number>, isAtBottom: true } },
    );

    expect(result.current.index).toBe(2);

    // Shrink length AND flip isAtBottom to false: wasAtBottom=true but length shrank
    // -> shouldStickToBottom is false, falls through to scroll-computed activeIndex (0).
    rerender({ indices: [0, 1] as ReadonlyArray<number>, isAtBottom: false });
    expect(result.current.index).toBe(0);
  });

  it("nav mode bypasses stick-to-bottom", () => {
    const virtualizer = createMockVirtualizer([
      { start: 0 },
      { start: 100 },
      { start: 200 },
      { start: 300 },
      { start: 400 },
    ]);
    const userPromptIndices = [0, 1, 2, 3, 4];

    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, true, machine),
    );

    // Nav mode suppresses stick-to-bottom, so the index follows the explicit
    // cursor instead of pinning to the last dot.  setIndex(1) forces it to 1.
    act(() => {
      result.current.setIndex(1);
    });

    expect(result.current.index).toBe(1);
  });

  it("setIndex opens a programmatic-scroll window that freezes the spy briefly", () => {
    // After setIndex, scroll events fired shortly after (e.g. from the
    // scrollToIndex that typically follows) must not clobber the just-set
    // cursor. The spy is frozen for ~500ms.
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);
    const userPromptIndices = [0, 1, 2];

    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, false, machine),
    );

    act(() => {
      result.current.setIndex(2);
    });
    expect(result.current.index).toBe(2);

    // Within the programmatic-scroll window, scroll events are ignored.
    act(() => {
      setScrollTop(container, 600);
      container.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    });

    expect(result.current.index).toBe(2);
  });

  it("regression: user wheel after setIndex unfreezes the spy so the dot rail tracks scroll", () => {
    // Regression for a bug where the scroll spy stayed frozen after a dot
    // click (setIndex), causing the active dot to stop tracking manual
    // scrolling. User-initiated scroll input must release the freeze.
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);
    const userPromptIndices = [0, 1, 2];

    // Nav mode is on (as if user just clicked a dot); stick-to-bottom is
    // suppressed so the scroll-derived index wins.
    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, false, machine),
    );

    act(() => {
      result.current.setIndex(0);
    });
    expect(result.current.index).toBe(0);

    // User wheels immediately — this must cancel the programmatic-scroll
    // freeze so subsequent scroll events update the cursor.
    act(() => {
      container.dispatchEvent(new Event("wheel"));
      setScrollTop(container, 600);
      container.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    });

    // With scrollTop=600 and threshold 200, active should be 1 (start=500 ≤ 800).
    expect(result.current.index).toBe(1);
  });

  it("spy resumes after the programmatic-scroll window expires", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);
    const userPromptIndices = [0, 1, 2];

    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, false, machine),
    );

    act(() => {
      result.current.setIndex(0);
    });
    expect(result.current.index).toBe(0);

    // Wait past the 500ms programmatic-scroll window without any user input.
    act(() => {
      vi.advanceTimersByTime(600);
    });

    // A scroll event after the window should update the cursor normally.
    act(() => {
      setScrollTop(container, 600);
      container.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    });

    expect(result.current.index).toBe(1);
  });

  it("touchstart/touchmove also cancel the programmatic-scroll freeze", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);

    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const { result } = renderHook(() =>
      useActivePromptIndex([0, 1, 2], virtualizer, scrollContainerRef, false, machine),
    );

    act(() => {
      result.current.setIndex(0);
    });

    // Simulate a touch gesture.
    act(() => {
      container.dispatchEvent(new Event("touchstart"));
      setScrollTop(container, 600);
      container.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    });

    expect(result.current.index).toBe(1);
  });

  it("setIndex updates the ref synchronously and the index after render", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 100 }, { start: 200 }, { start: 300 }]);
    const userPromptIndices = [0, 1, 2, 3];

    machine.dispatch({ kind: "navStarted", promptIndex: 0 }); // keep compute() from overwriting

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, false, machine),
    );

    // Capture the ref object before calling setIndex — it's the same identity across renders.
    const refObj = result.current.ref;

    act(() => {
      result.current.setIndex(3);
      // Ref mutated synchronously inside setIndex, BEFORE React re-renders.
      expect(refObj.current).toBe(3);
    });

    // After the render completes, index is also 3.
    expect(result.current.index).toBe(3);
    expect(result.current.ref.current).toBe(3);
  });

  it("stick-to-bottom overrides setIndex when not navigating", () => {
    const virtualizer = createMockVirtualizer([
      { start: 0 },
      { start: 100 },
      { start: 200 },
      { start: 300 },
      { start: 400 },
    ]);
    const userPromptIndices = [0, 1, 2, 3, 4];

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, true, machine),
    );

    expect(result.current.index).toBe(4);

    act(() => {
      result.current.setIndex(1);
    });

    // not navigating -> stick-to-bottom wins -> index = last = 4
    expect(result.current.index).toBe(4);
  });

  describe("isScrolledPastActive", () => {
    it("returns true when scrollTop is past the active prompt's start", () => {
      const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);

      const { result } = renderHook(() =>
        useActivePromptIndex([0, 1, 2], virtualizer, scrollContainerRef, false, machine),
      );

      // Pin active to index 1 (start=500) and scroll well below it.
      machine.dispatch({ kind: "navStarted", promptIndex: 0 });
      act(() => result.current.setIndex(1));
      setScrollTop(container, 800);

      expect(result.current.isScrolledPastActive()).toBe(true);
    });

    it("returns false when scrollTop is at (or within tolerance of) the active prompt's start", () => {
      const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);

      const { result } = renderHook(() =>
        useActivePromptIndex([0, 1, 2], virtualizer, scrollContainerRef, false, machine),
      );

      machine.dispatch({ kind: "navStarted", promptIndex: 0 });
      act(() => result.current.setIndex(1));
      // Exactly at the start — not scrolled past.
      setScrollTop(container, 500);
      expect(result.current.isScrolledPastActive()).toBe(false);

      // Within the 20px tolerance — still not "past".
      setScrollTop(container, 515);
      expect(result.current.isScrolledPastActive()).toBe(false);
    });

    it("returns false when the active index is out of range", () => {
      const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }]);

      const { result } = renderHook(() => useActivePromptIndex([], virtualizer, scrollContainerRef, false, machine));

      setScrollTop(container, 1000);
      expect(result.current.isScrolledPastActive()).toBe(false);
    });

    it("returns false when the scroll container is not mounted", () => {
      const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }]);
      const emptyRef: RefObject<HTMLDivElement | null> = { current: null };

      const { result } = renderHook(() => useActivePromptIndex([0, 1], virtualizer, emptyRef, false, machine));

      expect(result.current.isScrolledPastActive()).toBe(false);
    });
  });

  it("no-ops gracefully when the scroll container ref is null on mount", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }]);
    const emptyRef: RefObject<HTMLDivElement | null> = { current: null };

    const { result } = renderHook(() => useActivePromptIndex([0, 1], virtualizer, emptyRef, false, machine));

    // With no container, the scroll-listener effect returns early.  The
    // hook still provides a stable API surface.
    expect(result.current.index).toBe(0);
    expect(typeof result.current.setIndex).toBe("function");
    expect(result.current.isScrolledPastActive()).toBe(false);
    // setIndex still works (it doesn't touch the container).
    machine.dispatch({ kind: "navStarted", promptIndex: 0 });
    act(() => result.current.setIndex(1));
    expect(result.current.index).toBe(1);
  });

  it("rapid consecutive setIndex calls within the programmatic-scroll window respect the latest", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);

    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const { result } = renderHook(() =>
      useActivePromptIndex([0, 1, 2], virtualizer, scrollContainerRef, false, machine),
    );

    act(() => {
      result.current.setIndex(0);
      result.current.setIndex(2);
      result.current.setIndex(1);
    });

    expect(result.current.index).toBe(1);
    expect(result.current.ref.current).toBe(1);

    // The freeze is still in effect — scrolling should not clobber.
    act(() => {
      setScrollTop(container, 900);
      container.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
    });
    expect(result.current.index).toBe(1);
  });

  it("flicker bridge holds through a new message arriving at the bottom", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }, { start: 1500 }]);

    const { result, rerender } = renderHook(
      ({ indices, isAtBottom }) => useActivePromptIndex(indices, virtualizer, scrollContainerRef, isAtBottom, machine),
      { initialProps: { indices: [0, 1, 2] as ReadonlyArray<number>, isAtBottom: true } },
    );

    // Pinned to last prompt (2).
    expect(result.current.index).toBe(2);

    // New user prompt arrives — length grows from 3 to 4 and isAtBottom briefly
    // flickers false while the virtualizer/autoscroll catches up. Bridge should
    // hold us at the new last dot (3), NOT fall back to scroll-derived 0.
    rerender({ indices: [0, 1, 2, 3] as ReadonlyArray<number>, isAtBottom: false });
    expect(result.current.index).toBe(3);
  });

  it("unmount during the programmatic-scroll window does not warn about setState-on-unmounted", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }, { start: 1000 }]);
    machine.dispatch({ kind: "navStarted", promptIndex: 0 });

    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result, unmount } = renderHook(() =>
      useActivePromptIndex([0, 1, 2], virtualizer, scrollContainerRef, false, machine),
    );

    act(() => {
      result.current.setIndex(2);
    });
    expect(result.current.index).toBe(2);

    // Unmount before the 500ms programmatic-scroll window expires.
    unmount();

    // Advance past the window — no timer callback should touch React state now.
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    const unmountWarnings = consoleErrorSpy.mock.calls.filter((args) => String(args[0] ?? "").includes("unmounted"));
    expect(unmountWarnings).toEqual([]);
    consoleErrorSpy.mockRestore();
  });

  it("compute() does not throw when a user-prompt index is missing from measurementsCache", () => {
    // Only index 0 has a cache entry; indices 1 and 2 are absent.
    const virtualizer = createMockVirtualizer([{ start: 0 }]);
    const userPromptIndices = [0, 1, 2];

    const { result } = renderHook(() =>
      useActivePromptIndex(userPromptIndices, virtualizer, scrollContainerRef, false, machine),
    );

    // A scroll event must not throw when dereferencing the missing entries.
    expect(() => {
      act(() => {
        setScrollTop(container, 200);
        container.dispatchEvent(new Event("scroll"));
        vi.advanceTimersByTime(SCROLL_THROTTLE_MS);
      });
    }).not.toThrow();

    // Implementation falls back to `start ?? 0` for missing entries, so all
    // indices appear to be at or before the scrollTop → active is the last.
    expect(result.current.index).toBe(2);
  });

  it("removes the scroll listener on unmount", () => {
    const virtualizer = createMockVirtualizer([{ start: 0 }, { start: 500 }]);
    const removeEventListenerSpy = vi.spyOn(container, "removeEventListener");

    const { unmount } = renderHook(() => useActivePromptIndex([0, 1], virtualizer, scrollContainerRef, false, machine));

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith("scroll", expect.any(Function));
  });
});
