import type { Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "~/api";
import { ChatMessageRole } from "~/api";
import { chatSearchQueryAtom, chatSearchVisibleAtom } from "~/common/state/atoms/chatSearch.ts";

import { useChatSearch } from "../useChatSearch.ts";

const makeMessage = (id: string, text: string): ChatMessage =>
  ({
    id,
    role: ChatMessageRole.ASSISTANT,
    content: [{ type: "text", text }],
  }) as unknown as ChatMessage;

/**
 * Create a mock virtualizer with configurable viewport state.
 *
 * @param visibleIndices - Message indices that are currently visible in the viewport.
 *   When set, `getVirtualItems` returns virtual items for these indices and the scroll
 *   element reports them as within the viewport bounds. Defaults to empty (nothing visible).
 */
const createMockVirtualizer = (visibleIndices: Array<number> = []): Virtualizer<HTMLDivElement, Element> => {
  const ITEM_HEIGHT = 100;
  const VIEWPORT_HEIGHT = 500;
  const scrollOffset = 0;

  return {
    scrollToIndex: vi.fn(),
    scrollOffset,
    scrollElement: { clientHeight: VIEWPORT_HEIGHT } as HTMLDivElement,
    getVirtualItems: () =>
      visibleIndices.map((index) => ({
        index,
        start: index * ITEM_HEIGHT,
        end: index * ITEM_HEIGHT + ITEM_HEIGHT,
        size: ITEM_HEIGHT,
        key: index,
        lane: 0,
      })),
  } as unknown as Virtualizer<HTMLDivElement, Element>;
};

const createTestWrapper = (
  store: ReturnType<typeof createStore>,
): (({ children }: { children: ReactNode }) => ReactNode) => {
  return ({ children }: { children: ReactNode }): ReactNode => <Provider store={store}>{children}</Provider>;
};

describe("useChatSearch", () => {
  it("returns empty matches when search is not visible", () => {
    const store = createStore();
    const messages = [makeMessage("1", "hello world")];
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    expect(result.current.totalMatchCount).toBe(0);
    expect(result.current.matches).toHaveLength(0);
    expect(result.current.isSearchVisible).toBe(false);
  });

  it("returns matches immediately when search is visible with query", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const messages = [makeMessage("1", "hello world"), makeMessage("2", "hello again")];
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    // Matches are computed synchronously from the query atom (ChatSearchBar
    // handles debouncing before writing to the atom).
    expect(result.current.totalMatchCount).toBe(2);
    expect(result.current.query).toBe("hello");
  });

  it("returns 0 of 0 for no results", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "xyz");

    const messages = [makeMessage("1", "hello world")];
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    expect(result.current.totalMatchCount).toBe(0);
    expect(result.current.activeIndex).toBe(0);
  });

  it("navigateToMatch calls scrollToIndex", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const messages = [makeMessage("1", "hello"), makeMessage("2", "hello again")];
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    act(() => {
      result.current.navigateToMatch(1);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(1, { align: "start" });
  });

  it("navigateToMatch wraps around", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const messages = [makeMessage("1", "hello"), makeMessage("2", "hello")];
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    // Navigate past the end (index 2 with 2 matches wraps to 0)
    act(() => {
      result.current.navigateToMatch(2);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(0, { align: "start" });
  });

  it("navigateToMatch skips scrolling when the target message is already visible", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const messages = [makeMessage("1", "hello world"), makeMessage("2", "hello again")];
    // Both message indices (0 and 1) are visible in the viewport
    const virtualizer = createMockVirtualizer([0, 1]);

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    act(() => {
      result.current.navigateToMatch(0);
    });
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();

    act(() => {
      result.current.navigateToMatch(1);
    });
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("navigateToMatch scrolls when the target message is not visible", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const messages = [makeMessage("1", "hello world"), makeMessage("2", "hello again")];
    // Only message index 0 is visible — message index 1 is off-screen
    const virtualizer = createMockVirtualizer([0]);

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    act(() => {
      result.current.navigateToMatch(1);
    });
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(1, { align: "start" });
  });

  it("search is scoped to provided messages only", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const messages = [makeMessage("1", "goodbye world")];
    const virtualizer = createMockVirtualizer();

    const { result } = renderHook(() => useChatSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    expect(result.current.totalMatchCount).toBe(0);
  });
});
