import type { VirtualItem, Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

import { createScrollStateMachine } from "../../scroll/scrollStateMachine.ts";
import { useAlphaScrollPersistence } from "../useAlphaScrollPersistence.ts";

const createMockScrollContainer = (scrollTop: number, scrollHeight: number, clientHeight: number): HTMLDivElement => {
  const el = document.createElement("div");
  Object.defineProperty(el, "scrollTop", { value: scrollTop, writable: true, configurable: true });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: clientHeight, writable: true, configurable: true });
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

const createMockVirtualizer = (
  virtualItems: Array<VirtualItem>,
  paddingEnd = 0,
): Virtualizer<HTMLDivElement, Element> => {
  return {
    getVirtualItems: vi.fn(() => virtualItems),
    scrollToIndex: vi.fn(),
    options: { paddingEnd },
  } as unknown as Virtualizer<HTMLDivElement, Element>;
};

const wrapperFor = (store: ReturnType<typeof createStore>) => {
  return ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;
};

describe("useAlphaScrollPersistence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
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

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
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

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
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

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
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

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
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

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
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
    const virtualItems = [createMockVirtualItem(0, 0, 200)];
    const virtualizer = createMockVirtualizer(virtualItems);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    // Pre-set a saved position in the middle
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
      wrapper: wrapperFor(store),
    });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(1, { align: "start" });
  });

  it("drives the machine through restoring -> userControlled", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([createMockVirtualItem(0, 0, 200)]);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    const machine = createScrollStateMachine();

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine), {
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
    const virtualizer = createMockVirtualizer([createMockVirtualItem(0, 0, 200)]);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, createScrollStateMachine()), {
      wrapper: wrapperFor(store),
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledTimes(1); // initial apply
    act(() => {
      vi.advanceTimersByTime(48);
    });
    expect(virtualizer.scrollToIndex).toHaveBeenCalledTimes(2); // re-assert after settle
  });

  it("skips the deferred re-assert when the user scrolls during restore", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer([createMockVirtualItem(0, 0, 200)]);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();
    store.set(alphaScrollPositionAtomFamily("task-1"), {
      firstVisibleMessageId: "msg-2",
      pixelOffset: 50,
      distanceFromBottom: 800,
    });
    const machine = createScrollStateMachine();

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages, machine), {
      wrapper: wrapperFor(store),
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledTimes(1); // initial apply

    // The user grabs the scroll before the re-assert frames drain.
    act(() => {
      machine.dispatch({ kind: "userScrolled" });
      vi.advanceTimersByTime(48);
    });

    // Re-assert skipped — the user's scroll is not clobbered.
    expect(virtualizer.scrollToIndex).toHaveBeenCalledTimes(1);
    expect(machine.getState().authority.kind).toBe("userControlled");
  });
});
