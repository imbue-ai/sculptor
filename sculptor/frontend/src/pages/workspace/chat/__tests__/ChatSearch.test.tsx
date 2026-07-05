import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { chatSearchFocusRequestAtom, chatSearchVisibleAtom } from "~/common/state/atoms/chatSearch.ts";

import { ChatSearch } from "../ChatSearch.tsx";

type Store = ReturnType<typeof createStore>;

const createWrapper = (): { wrapper: ({ children }: { children: ReactNode }) => ReactNode; store: Store } => {
  const store = createStore();
  store.set(chatSearchVisibleAtom, true);
  return {
    store,
    wrapper: ({ children }: { children: ReactNode }): ReactNode => <Provider store={store}>{children}</Provider>,
  };
};

describe("ChatSearch", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders search input", () => {
    const { wrapper } = createWrapper();
    render(<ChatSearch totalMatchCount={5} activeIndex={2} navigateToMatch={vi.fn()} />, { wrapper });
    expect(screen.getByTestId(ElementIds.CHAT_SEARCH_INPUT)).toBeInTheDocument();
  });

  it("renders match counter", () => {
    const { wrapper } = createWrapper();
    render(<ChatSearch totalMatchCount={5} activeIndex={2} navigateToMatch={vi.fn()} />, { wrapper });
    expect(screen.getByTestId(ElementIds.CHAT_SEARCH_MATCH_COUNTER)).toBeInTheDocument();
  });

  it("renders search bar container", () => {
    const { wrapper } = createWrapper();
    render(<ChatSearch totalMatchCount={0} activeIndex={0} navigateToMatch={vi.fn()} />, { wrapper });
    expect(screen.getByTestId(ElementIds.CHAT_SEARCH_BAR)).toBeInTheDocument();
  });

  it("calls navigateToMatch on Enter", async () => {
    const navigateToMatch = vi.fn();
    const { wrapper } = createWrapper();
    render(<ChatSearch totalMatchCount={5} activeIndex={2} navigateToMatch={navigateToMatch} />, {
      wrapper,
    });

    const input = screen.getByTestId(ElementIds.CHAT_SEARCH_INPUT);
    await userEvent.type(input, "test");
    await userEvent.keyboard("{Enter}");

    expect(navigateToMatch).toHaveBeenCalledWith(3); // activeIndex + 1
  });

  it("calls navigateToMatch with previous on Shift+Enter", async () => {
    const navigateToMatch = vi.fn();
    const { wrapper } = createWrapper();
    render(<ChatSearch totalMatchCount={5} activeIndex={2} navigateToMatch={navigateToMatch} />, {
      wrapper,
    });

    const input = screen.getByTestId(ElementIds.CHAT_SEARCH_INPUT);
    await userEvent.type(input, "test");
    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");

    expect(navigateToMatch).toHaveBeenCalledWith(1); // activeIndex - 1
  });

  // Regression: incrementing the focus-request atom must re-focus the input.
  // The effect previously depended on a stable useSetAtom setter, so it never
  // re-fired; with useAtomValue the changed atom value re-runs the effect.
  it("re-focuses the input when the focus-request atom changes", () => {
    const { wrapper, store } = createWrapper();
    render(<ChatSearch totalMatchCount={5} activeIndex={2} navigateToMatch={vi.fn()} />, { wrapper });

    const input = screen.getByTestId(ElementIds.CHAT_SEARCH_INPUT);
    // Move focus away so the re-focus effect has something to do.
    act(() => (document.activeElement as HTMLElement | null)?.blur());
    expect(document.activeElement).not.toBe(input);

    // Bump the focus-request atom: the effect should re-fire and refocus.
    act(() => store.set(chatSearchFocusRequestAtom, store.get(chatSearchFocusRequestAtom) + 1));

    expect(document.activeElement).toBe(input);
  });
});
