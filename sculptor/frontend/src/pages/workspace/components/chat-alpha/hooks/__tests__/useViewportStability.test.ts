import type { VirtualItem, Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useViewportStability } from "../useViewportStability.ts";

const createMockScrollContainer = (scrollTop: number, scrollHeight: number): HTMLDivElement => {
  const el = document.createElement("div");
  Object.defineProperty(el, "scrollTop", { value: scrollTop, writable: true, configurable: true });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
  return el;
};

const createMockVirtualItem = (index: number, start: number, size: number): VirtualItem => ({
  index,
  start,
  size,
  end: start + size,
  key: index,
  lane: 0,
});

const createMockVirtualizer = (virtualItems: Array<VirtualItem>): Virtualizer<HTMLDivElement, Element> => {
  return {
    getVirtualItems: vi.fn(() => virtualItems),
  } as unknown as Virtualizer<HTMLDivElement, Element>;
};

describe("useViewportStability", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("adjusts scrollTop when item above viewport changes height", () => {
    // scrollTop=500, first visible item starts at 400 with size 200 (end=600 > 500)
    const el = createMockScrollContainer(500, 2000);
    const ref = { current: el };
    const isProgrammaticRef = { current: false };

    const virtualItems = [
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200), // first visible (start + size = 600 > scrollTop 500)
      createMockVirtualItem(3, 600, 200),
    ];
    const virtualizer = createMockVirtualizer(virtualItems);

    const { result } = renderHook(() => useViewportStability(ref, virtualizer, isProgrammaticRef));

    // Trigger height change for item index 0 (above viewport)
    act(() => {
      result.current.onHeightChange(0);
    });

    // Simulate DOM update: scrollHeight increases by 100
    Object.defineProperty(el, "scrollHeight", { value: 2100, writable: true, configurable: true });

    act(() => {
      vi.advanceTimersByTime(16); // rAF
    });

    expect(el.scrollTop).toBe(600); // 500 + 100 delta
    expect(isProgrammaticRef.current).toBe(true);
  });

  it("does not adjust scrollTop when item within viewport changes height", () => {
    const el = createMockScrollContainer(500, 2000);
    const ref = { current: el };
    const isProgrammaticRef = { current: false };

    const virtualItems = [createMockVirtualItem(2, 400, 200), createMockVirtualItem(3, 600, 200)];
    const virtualizer = createMockVirtualizer(virtualItems);

    const { result } = renderHook(() => useViewportStability(ref, virtualizer, isProgrammaticRef));

    // Trigger height change for item index 2 (within viewport, first visible)
    act(() => {
      result.current.onHeightChange(2);
    });

    // scrollTop should remain unchanged
    expect(el.scrollTop).toBe(500);
  });

  it("does not adjust scrollTop when item below viewport changes height", () => {
    const el = createMockScrollContainer(500, 2000);
    const ref = { current: el };
    const isProgrammaticRef = { current: false };

    const virtualItems = [createMockVirtualItem(2, 400, 200), createMockVirtualItem(3, 600, 200)];
    const virtualizer = createMockVirtualizer(virtualItems);

    const { result } = renderHook(() => useViewportStability(ref, virtualizer, isProgrammaticRef));

    // Trigger height change for item index 3 (below first visible)
    act(() => {
      result.current.onHeightChange(3);
    });

    expect(el.scrollTop).toBe(500);
  });

  it("decreases scrollTop when item above viewport collapses", () => {
    const el = createMockScrollContainer(500, 2000);
    const ref = { current: el };
    const isProgrammaticRef = { current: false };

    const virtualItems = [createMockVirtualItem(0, 0, 200), createMockVirtualItem(2, 400, 200)];
    const virtualizer = createMockVirtualizer(virtualItems);

    const { result } = renderHook(() => useViewportStability(ref, virtualizer, isProgrammaticRef));

    act(() => {
      result.current.onHeightChange(0);
    });

    // Simulate collapse: scrollHeight decreases by 80
    Object.defineProperty(el, "scrollHeight", { value: 1920, writable: true, configurable: true });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    expect(el.scrollTop).toBe(420); // 500 - 80 delta
  });
});
