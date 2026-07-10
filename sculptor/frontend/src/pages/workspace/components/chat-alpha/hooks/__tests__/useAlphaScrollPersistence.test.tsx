import type { VirtualItem, Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

import { createScrollStateMachine } from "../../scroll/scrollStateMachine.ts";
import { useAlphaScrollPersistence } from "../useAlphaScrollPersistence.ts";

type MockScrollContainer = HTMLDivElement & { scrollTopWrites: Array<number> };

const createMockScrollContainer = (
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
): MockScrollContainer => {
  const el = document.createElement("div") as MockScrollContainer;
  // Track every scrollTop assignment so tests can count applies (the real
  // browser fires no scroll event for equal-value writes, so counting writes
  // is the only observable signal for "how many times did the restore apply").
  el.scrollTopWrites = [];
  let currentScrollTop = scrollTop;
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => currentScrollTop,
    set: (value: number) => {
      currentScrollTop = value;
      el.scrollTopWrites.push(value);
    },
  });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: clientHeight, writable: true, configurable: true });
  return el;
};

const setScrollPosition = (el: HTMLDivElement, scrollTop: number, scrollHeight: number): void => {
  Object.defineProperty(el, "scrollTop", { value: scrollTop, writable: true, configurable: true });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
};

const createMockVirtualItem = (index: number, start: number, size: number): VirtualItem => ({
  index,
  start,
  size,
  end: start + size,
  key: index,
  lane: 0,
});

const createMockVirtualizer = (
  virtualItems: Array<VirtualItem>,
  paddingEnd = 0,
): Virtualizer<HTMLDivElement, Element> => {
  return {
    getVirtualItems: vi.fn(() => virtualItems),
    getTotalSize: vi.fn(() => 0),
    measureElement: vi.fn(),
    measurementsCache: virtualItems,
    scrollOffset: 0,
    options: { paddingEnd },
  } as unknown as Virtualizer<HTMLDivElement, Element>;
};

const wrapperFor = (store: ReturnType<typeof createStore>) => {
  return ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;
};

describe("useAlphaScrollPersistence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // The scroll-position atom is localStorage-backed (survives app
    // restarts); clear it so saves from one test don't leak into the next.
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("scrolls to the padded max scroll on first visit (no saved position)", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualItems = [createMockVirtualItem(0, 0, 200)];
    // paddingEnd 400 distinguishes the max scroll (1500) from the content
    // bottom (1100): a first visit lands at the very end of the padded range —
    // the anchored-turn rest position when the last turn is short.
    const virtualizer = createMockVirtualizer(virtualItems, 400);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    // Initial mount triggers restore
    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Restored to the max scroll offset (scrollHeight 2000 - clientHeight 500).
    expect(el.scrollTop).toBe(1500);
  });

  it("saves scroll position on scroll events", () => {
    const el = createMockScrollContainer(300, 2000, 500);
    const ref = { current: el };
    const virtualItems = [
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200),
    ];
    const virtualizer = createMockVirtualizer(virtualItems);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    // Wait for restore to complete (double rAF) so the machine leaves `restoring`.
    act(() => {
      vi.advanceTimersByTime(48);
    });

    // The restore-to-bottom moved scrollTop; put it where this test's user scroll
    // lands (item index 1 spans it) before recording the position.
    el.scrollTop = 300;

    // Trigger scroll
    act(() => {
      el.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(16); // rAF debounce
    });

    const savedPosition = store.get(alphaScrollPositionAtomFamily("task-1"));
    expect(savedPosition).toBeDefined();
    expect(savedPosition?.firstVisibleMessageId).toBe("msg-2"); // item at index 1 (start=200, end=400 > scrollTop=300)
    expect(savedPosition?.pixelOffset).toBe(100); // 300 - 200
    expect(savedPosition?.distanceFromBottom).toBe(1200); // 2000 - 300 - 500
  });

  it("restores to the saved distance from the content bottom when near the bottom", () => {
    // Desktop-height container (>= 700px), where the at-bottom threshold is
    // 200px — so the saved 100px distance takes the near-bottom restore path.
    const el = createMockScrollContainer(0, 2000, 800);
    const ref = { current: el };
    const virtualItems = [createMockVirtualItem(0, 0, 200)];
    const virtualizer = createMockVirtualizer(virtualItems);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    // Pre-set a saved position that was near bottom
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-3",
      pixelOffset: 0,
      distanceFromBottom: 100, // within threshold
    });

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Restored 100px above the content bottom (2000 - paddingEnd 0 - 800 - 100),
    // relative to the *current* content bottom so content that grew while away
    // stays in view.
    expect(el.scrollTop).toBe(1100);
  });

  it("round-trips a position inside the tail padding (negative distance)", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualItems = [createMockVirtualItem(0, 0, 200)];
    const virtualizer = createMockVirtualizer(virtualItems, 400);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    // Saved while scrolled 300px past the content bottom, into the padding —
    // e.g. the anchored-turn rest position or a manual max scroll.
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-3",
      pixelOffset: 0,
      distanceFromBottom: -300,
    });

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Content bottom (2000 - 400 - 500 = 1100) plus the 300px into the padding.
    expect(el.scrollTop).toBe(1400);
  });

  it("clamps a padding-deep saved position to the current scroll range", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualItems = [createMockVirtualItem(0, 0, 200)];
    // paddingEnd shrank since the save (e.g. the tail grew while away): the
    // saved 600px-into-the-padding position no longer exists.
    const virtualizer = createMockVirtualizer(virtualItems, 400);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-3",
      pixelOffset: 0,
      distanceFromBottom: -600,
    });

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Content bottom 1100 + 600 = 1700 exceeds the max scroll (1500) — clamped.
    expect(el.scrollTop).toBe(1500);
  });

  it("restores to message position when saved", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualItems = [
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200),
    ];
    const virtualizer = createMockVirtualizer(virtualItems);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    // Pre-set a saved position in the middle
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    // Anchor start (200) + pixel offset (50), resolved from the measurements
    // as one absolute write — not via scrollToIndex, whose reconcile loop
    // would keep re-driving scrollTop toward the bare item start.
    expect(el.scrollTop).toBe(250);
  });

  it("drives the machine through restoring -> userControlled", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([createMockVirtualItem(0, 0, 200)]);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    const machine = createScrollStateMachine();

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    // Mount restore puts the machine into `restoring` synchronously.
    expect(machine.getState().authority.kind).toBe("restoring");

    // The deferred re-assert settles it back to `userControlled`.
    act(() => {
      vi.advanceTimersByTime(48);
    });
    expect(machine.getState().authority.kind).toBe("userControlled");
  });

  it("re-asserts the saved position after settle when the user stays put", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200),
    ]);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    // Mount restore: the estimate apply plus the pre-paint settle apply.
    expect(el.scrollTopWrites).toHaveLength(2);
    act(() => {
      vi.advanceTimersByTime(48);
    });
    // The deferred safety-net re-assert after the settle frames.
    expect(el.scrollTopWrites).toHaveLength(3);
    expect(el.scrollTop).toBe(250);
  });

  it("skips the deferred re-assert when the user scrolls during restore", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200),
    ]);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });
    const machine = createScrollStateMachine();

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    // Mount restore: the estimate apply plus the pre-paint settle apply.
    expect(el.scrollTopWrites).toHaveLength(2);

    // The user grabs the scroll before the re-assert frames drain.
    act(() => {
      machine.dispatch({ kind: "userScrolled" });
      vi.advanceTimersByTime(48);
    });

    // Re-assert skipped — the user's scroll is not clobbered.
    expect(el.scrollTopWrites).toHaveLength(2);
    expect(machine.getState().authority.kind).toBe("userControlled");
  });

  it("settles against swept measurements before the deferred re-assert frames", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    // Real DOM structure for the sweep: content wrapper containing one mounted
    // row, so querySelectorAll("[data-index]") finds it.
    const content = document.createElement("div");
    const row = document.createElement("div");
    row.setAttribute("data-index", "1");
    content.appendChild(row);
    el.appendChild(content);
    const ref = { current: el };

    const virtualItems = [
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200),
    ];
    const virtualizer = createMockVirtualizer(virtualItems);
    // Sweeping the mounted row shifts the anchor's measured start from 200 to
    // 400 — the way real measurements replace estimates on a task switch.
    (virtualizer.measureElement as ReturnType<typeof vi.fn>).mockImplementation(() => {
      virtualItems[1] = createMockVirtualItem(1, 400, 200);
    });

    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    // Without advancing any timers: the estimate apply landed at 250, and the
    // pre-paint settle re-applied at the swept position 450 — the first painted
    // frame is already the settled one.
    expect(virtualizer.measureElement).toHaveBeenCalledWith(row);
    expect(el.scrollTopWrites).toEqual([250, 450]);
  });

  it("holds the restore pending until messages arrive, then applies it", () => {
    // Right after a task switch the task-detail atom can still be cold: the
    // chat renders with zero messages while the unified stream fills it in.
    // The restore must wait for the messages instead of being skipped.
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([createMockVirtualItem(0, 0, 200), createMockVirtualItem(1, 200, 200)]);
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });
    const machine = createScrollStateMachine();
    const loadedMessages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];

    const { rerender } = renderHook(
      ({ messages }: { messages: Array<{ id: string }> }) =>
        useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }),
      { wrapper: wrapperFor(store), initialProps: { messages: [] as Array<{ id: string }> } },
    );

    // The wait is armed: the machine already owns the window (suppressing
    // saves), but nothing has been applied against the empty list.
    expect(machine.getState().authority.kind).toBe("restoring");
    expect(el.scrollTopWrites).toHaveLength(0);

    // Messages arrive — the pending restore fires against them: the anchor
    // (start 200 + pixel offset 50) resolved as an absolute write.
    rerender({ messages: loadedMessages });
    expect(el.scrollTop).toBe(250);

    act(() => {
      vi.advanceTimersByTime(48);
    });
    expect(machine.getState().authority.kind).toBe("userControlled");
  });

  it("does not overwrite the saved position while the restore is pending", () => {
    // The interim landing before messages arrive (content mounting, pins
    // against estimates) fires scroll events; none of them may clobber the
    // saved position the pending restore has yet to read.
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([createMockVirtualItem(0, 0, 200)]);
    const store = createStore();
    const saved = {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    };
    store.set(alphaScrollPositionAtomFamily("task-1"), saved);

    const machine = createScrollStateMachine();
    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", [], machine, { current: false }), {
      wrapper: wrapperFor(store),
    });

    act(() => {
      setScrollPosition(el, 700, 2000);
      el.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(48);
    });

    expect(store.get(alphaScrollPositionAtomFamily("task-1"))).toEqual(saved);
  });

  it("skips the pending restore when the user scrolls during the wait", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([createMockVirtualItem(1, 200, 200)]);
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });
    const machine = createScrollStateMachine();

    const { rerender } = renderHook(
      ({ messages }: { messages: Array<{ id: string }> }) =>
        useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, { current: false }),
      { wrapper: wrapperFor(store), initialProps: { messages: [] as Array<{ id: string }> } },
    );

    // The user takes over before the messages land.
    act(() => {
      machine.dispatch({ kind: "userScrolled" });
    });

    rerender({ messages: [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }] });

    // Their position wins: the late restore never fires.
    expect(el.scrollTopWrites).toHaveLength(0);
    expect(machine.getState().authority.kind).toBe("userControlled");
  });

  it("does not save positions produced by programmatic scrolls", () => {
    const el = createMockScrollContainer(300, 2000, 500);
    const ref = { current: el };
    const virtualItems = [
      createMockVirtualItem(0, 0, 200),
      createMockVirtualItem(1, 200, 200),
      createMockVirtualItem(2, 400, 200),
    ];
    const virtualizer = createMockVirtualizer(virtualItems);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    const isProgrammaticScrollRef = { current: false };

    const machine = createScrollStateMachine();
    renderHook(
      () => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine, isProgrammaticScrollRef),
      {
        wrapper: wrapperFor(store),
      },
    );

    // Let the mount restore settle so the machine no longer suppresses saves.
    act(() => {
      vi.advanceTimersByTime(48);
    });

    // A pin / TanStack compensation scroll: flagged programmatic — not saved.
    act(() => {
      isProgrammaticScrollRef.current = true;
      setScrollPosition(el, 300, 2000);
      el.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(16);
    });
    expect(store.get(alphaScrollPositionAtomFamily("task-1"))).toBeNull();

    // The same scroll from the user is saved.
    act(() => {
      isProgrammaticScrollRef.current = false;
      el.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(16);
    });
    expect(store.get(alphaScrollPositionAtomFamily("task-1"))?.firstVisibleMessageId).toBe("msg-2");
  });
});
