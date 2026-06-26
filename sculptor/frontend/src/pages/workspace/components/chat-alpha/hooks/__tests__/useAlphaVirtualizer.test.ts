import type { VirtualItem, Virtualizer } from "@tanstack/react-virtual";
import { describe, expect, it } from "vitest";

import {
  buildShouldAdjustScrollPositionOnItemSizeChange,
  shouldAdjustScrollPosition,
  skipNextScrollAdjustForItem,
  touchLRU,
} from "../useAlphaVirtualizer.ts";

const createMockItem = (start: number, size: number): VirtualItem => ({
  index: 0,
  start,
  end: start + size,
  size,
  key: "0",
  lane: 0,
});

const createMockInstance = (scrollOffset: number): Virtualizer<HTMLDivElement, Element> =>
  ({
    scrollOffset,
  }) as unknown as Virtualizer<HTMLDivElement, Element>;

describe("shouldAdjustScrollPosition", () => {
  it("adjusts when item is entirely above the viewport", () => {
    // Item: start=100, size=200 → end=300.  scrollOffset=400.
    // Item is entirely above viewport → should adjust.
    const item = createMockItem(100, 200);
    const instance = createMockInstance(400);
    expect(shouldAdjustScrollPosition(item, 50, instance)).toBe(true);
  });

  it("does NOT adjust when item overlaps the viewport (streaming message jitter)", () => {
    // Item: start=500, size=800 → end=1300.  scrollOffset=700.
    // The top of the item is above the viewport but the item extends into it.
    // Growing this item from the bottom should NOT shift the visible content.
    const item = createMockItem(500, 800);
    const instance = createMockInstance(700);
    expect(shouldAdjustScrollPosition(item, 100, instance)).toBe(false);
  });

  it("does NOT adjust when item starts at the viewport edge", () => {
    // Item starts exactly at scrollOffset → it's the first visible item.
    const item = createMockItem(400, 300);
    const instance = createMockInstance(400);
    expect(shouldAdjustScrollPosition(item, 50, instance)).toBe(false);
  });

  it("does NOT adjust when item is below the viewport", () => {
    // Item is well below the scroll position.
    const item = createMockItem(2000, 120);
    const instance = createMockInstance(500);
    expect(shouldAdjustScrollPosition(item, 30, instance)).toBe(false);
  });

  it("adjusts when item ends exactly at the scroll offset", () => {
    // Item: start=100, size=300 → end=400.  scrollOffset=400.
    // Item ends right at the viewport top → entirely above → should adjust.
    const item = createMockItem(100, 300);
    const instance = createMockInstance(400);
    expect(shouldAdjustScrollPosition(item, 20, instance)).toBe(true);
  });

  it("does NOT adjust an in-view item that grew, regardless of delta", () => {
    // TanStack hands the predicate the *cached* (pre-growth) measurement, so
    // item.size=420 is the size before this resize and the pre-growth end is
    // start + size = 520. scrollOffset=400 → the item was visible → no adjust.
    const item = createMockItem(100, 420);
    const instance = createMockInstance(400);
    expect(shouldAdjustScrollPosition(item, 50, instance)).toBe(false);
  });

  it("does NOT adjust the in-view reading anchor even when it grew by more than its height (SCU-1566)", () => {
    // The reading anchor at the top: start=277, cached (pre-growth) size=2588,
    // scrollOffset=0. Pre-growth end = 277 + 2588 = 2865 > 0 → in view → no adjust.
    // The old formula subtracted delta (277 + 2588 - 3150 = -285 ≤ 0) and wrongly
    // compensated, jumping the view down ~3150px on a narrowing width reflow.
    const item = createMockItem(277, 2588);
    const instance = createMockInstance(0);
    expect(shouldAdjustScrollPosition(item, 3150, instance)).toBe(false);
  });
});

describe("buildShouldAdjustScrollPositionOnItemSizeChange", () => {
  const notMeasuring = (): boolean => false;
  const measuring = (): boolean => true;

  it("flags the programmatic-scroll ref when about to adjust scrollTop", () => {
    // TanStack Virtual fires a scroll event when this callback returns true.
    // Without the flag, chat-level scroll listeners treat it as user intent
    // and dismiss click-pinned popovers.
    const isProgrammaticScrollRef = { current: false };
    const adjust = buildShouldAdjustScrollPositionOnItemSizeChange(notMeasuring, isProgrammaticScrollRef);

    const item = createMockItem(100, 200);
    const instance = createMockInstance(400);
    expect(adjust(item, 50, instance)).toBe(true);
    expect(isProgrammaticScrollRef.current).toBe(true);
  });

  it("does not touch the flag when no adjustment is needed", () => {
    const isProgrammaticScrollRef = { current: false };
    const adjust = buildShouldAdjustScrollPositionOnItemSizeChange(notMeasuring, isProgrammaticScrollRef);

    // Item overlapping the viewport → no adjustment.
    const item = createMockItem(500, 800);
    const instance = createMockInstance(700);
    expect(adjust(item, 100, instance)).toBe(false);
    expect(isProgrammaticScrollRef.current).toBe(false);
  });

  it("returns false (and skips the flag) while the layout is measuring after a task switch", () => {
    const isProgrammaticScrollRef = { current: false };
    const adjust = buildShouldAdjustScrollPositionOnItemSizeChange(measuring, isProgrammaticScrollRef);

    const item = createMockItem(100, 200);
    const instance = createMockInstance(400);
    expect(adjust(item, 50, instance)).toBe(false);
    expect(isProgrammaticScrollRef.current).toBe(false);
  });

  it("honours skipNextScrollAdjustForItem and does not flag the ref", () => {
    const isProgrammaticScrollRef = { current: false };
    const adjust = buildShouldAdjustScrollPositionOnItemSizeChange(notMeasuring, isProgrammaticScrollRef);

    const item: VirtualItem = { ...createMockItem(100, 200), index: 7, key: "7" };
    const instance = createMockInstance(400);
    skipNextScrollAdjustForItem(7);
    expect(adjust(item, 50, instance)).toBe(false);
    expect(isProgrammaticScrollRef.current).toBe(false);

    // Consume-once semantics: the next call for the same index resumes normal behavior.
    expect(adjust(item, 50, instance)).toBe(true);
    expect(isProgrammaticScrollRef.current).toBe(true);
  });

  it("works without a programmatic-scroll ref (back-compat for callers that opt out)", () => {
    const adjust = buildShouldAdjustScrollPositionOnItemSizeChange(notMeasuring);

    const item = createMockItem(100, 200);
    const instance = createMockInstance(400);
    expect(() => adjust(item, 50, instance)).not.toThrow();
    expect(adjust(item, 50, instance)).toBe(true);
  });
});

describe("touchLRU", () => {
  it("moves an existing key to the end of the map", () => {
    const map = new Map([
      ["a", 1],
      ["b", 2],
      ["c", 3],
    ]);
    touchLRU(map, "a", 5);
    expect([...map.keys()]).toEqual(["b", "c", "a"]);
  });

  it("does not alter the map when the key is not present", () => {
    const map = new Map([
      ["a", 1],
      ["b", 2],
    ]);
    touchLRU(map, "z", 5);
    expect([...map.keys()]).toEqual(["a", "b"]);
    expect(map.size).toBe(2);
  });

  it("evicts the oldest entry when the map exceeds maxSize", () => {
    const map = new Map([
      ["a", 1],
      ["b", 2],
      ["c", 3],
    ]);
    // Touch "b" (moves to end), but maxSize=2 → "a" is evicted.
    touchLRU(map, "b", 2);
    expect(map.has("a")).toBe(false);
    expect([...map.keys()]).toEqual(["c", "b"]);
  });

  it("does not evict when exactly at maxSize", () => {
    const map = new Map([
      ["a", 1],
      ["b", 2],
    ]);
    touchLRU(map, "a", 2);
    expect(map.size).toBe(2);
    expect([...map.keys()]).toEqual(["b", "a"]);
  });

  it("preserves the value when moving a key", () => {
    const map = new Map([
      ["a", 42],
      ["b", 99],
    ]);
    touchLRU(map, "a", 5);
    expect(map.get("a")).toBe(42);
  });
});
