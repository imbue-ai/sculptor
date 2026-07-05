import type { Virtualizer } from "@tanstack/react-virtual";
import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "~/api";
import { ChatMessageRole } from "~/api";
import { chatSearchQueryAtom, chatSearchVisibleAtom } from "~/common/state/atoms/chatSearch.ts";

import { useAlphaAutoScroll } from "../useAlphaAutoScroll.ts";
import { useAlphaSearch } from "../useAlphaSearch.ts";

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
  el.appendChild(document.createElement("div"));
  Object.defineProperty(el, "scrollTop", { value: scrollTop, writable: true, configurable: true });
  Object.defineProperty(el, "scrollHeight", { value: scrollHeight, writable: true, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: clientHeight, writable: true, configurable: true });
  return el;
};

const createMockVirtualizer = (): Virtualizer<HTMLDivElement, Element> =>
  ({
    scrollToIndex: vi.fn(),
    options: { paddingEnd: 0 },
  }) as unknown as Virtualizer<HTMLDivElement, Element>;

const makeMessage = (id: string, text: string): ChatMessage =>
  ({
    id,
    role: ChatMessageRole.ASSISTANT,
    content: [{ type: "text", text }],
  }) as unknown as ChatMessage;

const createTestWrapper = (
  store: ReturnType<typeof createStore>,
): (({ children }: { children: ReactNode }) => ReactNode) => {
  return ({ children }: { children: ReactNode }): ReactNode => <Provider store={store}>{children}</Provider>;
};

// Mirrors the AlphaChatInterface wiring:
// useAlphaAutoScroll + useAlphaSearch + the search-suppression effect.
const useSearchSuppression = (
  scrollContainerRef: React.RefObject<HTMLDivElement | null>,
  isStreaming: boolean,
  messageCount: number,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  messages: ReadonlyArray<ChatMessage>,
): { isSuppressed: boolean; isEngaged: boolean } => {
  const { isSuppressed, setIsSuppressed } = useAlphaAutoScroll(
    scrollContainerRef,
    isStreaming,
    messageCount,
    virtualizer,
    null,
    -1,
    "test-task",
  );
  const { isSearchVisible } = useAlphaSearch(messages, virtualizer);

  useEffect(() => {
    if (isSearchVisible) {
      setIsSuppressed(true);
    } else {
      setIsSuppressed(false);
    }
  }, [isSearchVisible, setIsSuppressed]);

  return { isSuppressed, isEngaged: false };
};

describe("search suppresses auto-scroll", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", MockResizeObserver);
    resizeObserverCallbacks.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("suppresses auto-scroll when search is visible", () => {
    const store = createStore();
    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();
    const messages = [makeMessage("1", "hello world")];

    const { result } = renderHook(() => useSearchSuppression(ref, true, 1, virtualizer, messages), {
      wrapper: createTestWrapper(store),
    });

    expect(result.current.isSuppressed).toBe(false);

    // Open search
    act(() => {
      store.set(chatSearchVisibleAtom, true);
      store.set(chatSearchQueryAtom, "hello");
    });

    expect(result.current.isSuppressed).toBe(true);
  });

  it("lifts suppression when search closes", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const el = createMockScrollContainer(1300, 2000, 500);
    const ref = { current: el };
    const virtualizer = createMockVirtualizer();
    const messages = [makeMessage("1", "hello world")];

    const { result } = renderHook(() => useSearchSuppression(ref, true, 1, virtualizer, messages), {
      wrapper: createTestWrapper(store),
    });

    expect(result.current.isSuppressed).toBe(true);

    // Close search
    act(() => {
      store.set(chatSearchVisibleAtom, false);
    });

    expect(result.current.isSuppressed).toBe(false);
  });

  it("search navigation still scrolls to matches while auto-scroll is suppressed", () => {
    const store = createStore();
    store.set(chatSearchVisibleAtom, true);
    store.set(chatSearchQueryAtom, "hello");

    const virtualizer = createMockVirtualizer();
    const messages = [makeMessage("1", "hello"), makeMessage("2", "hello again")];

    const { result: searchResult } = renderHook(() => useAlphaSearch(messages, virtualizer), {
      wrapper: createTestWrapper(store),
    });

    // Navigate to match — should scroll even though auto-scroll would be suppressed
    act(() => {
      searchResult.current.navigateToMatch(1);
    });

    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(1, { align: "start" });
  });
});
