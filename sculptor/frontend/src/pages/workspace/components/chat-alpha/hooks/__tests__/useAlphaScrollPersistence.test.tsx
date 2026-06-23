import type { VirtualItem, Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

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

const createMockVirtualizer = (virtualItems: Array<VirtualItem>): Virtualizer<HTMLDivElement, Element> => {
  return {
    getVirtualItems: vi.fn(() => virtualItems),
    scrollToIndex: vi.fn(),
  } as unknown as Virtualizer<HTMLDivElement, Element>;
};

describe("useAlphaScrollPersistence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("scrolls to bottom on first visit (no saved position)", () => {
    const el = createMockScrollContainer(0, 2000, 500);
    const ref = { current: el };
    const virtualItems = [createMockVirtualItem(0, 0, 200)];
    const virtualizer = createMockVirtualizer(virtualItems);
    const messages = [{ id: "msg-1" }, { id: "msg-2" }, { id: "msg-3" }];
    const store = createStore();

    const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
      <Provider store={store}>{children}</Provider>
    );

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages), { wrapper });

    // Initial mount triggers restore
    act(() => {
      vi.advanceTimersByTime(16);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(2, { align: "end" });
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

    const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
      <Provider store={store}>{children}</Provider>
    );

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages), { wrapper });

    // Wait for restore to complete (double rAF)
    act(() => {
      vi.advanceTimersByTime(48);
    });

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

  it("restores to bottom when user was within 200px of bottom", () => {
    const el = createMockScrollContainer(0, 2000, 500);
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

    const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
      <Provider store={store}>{children}</Provider>
    );

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages), { wrapper });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(2, { align: "end" });
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

    const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
      <Provider store={store}>{children}</Provider>
    );

    renderHook(() => useAlphaScrollPersistence(ref, virtualizer, "task-1", messages), { wrapper });

    act(() => {
      vi.advanceTimersByTime(16);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(1, { align: "start" });
  });
});
