import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { chatSearchVisibleAtom } from "~/common/state/atoms/chatSearch.ts";

import { AlphaSearchBar } from "../AlphaSearchBar.tsx";

const createWrapper = (): { wrapper: ({ children }: { children: ReactNode }) => ReactNode } => {
  const store = createStore();
  store.set(chatSearchVisibleAtom, true);
  return {
    wrapper: ({ children }: { children: ReactNode }): ReactNode => <Provider store={store}>{children}</Provider>,
  };
};

describe("AlphaSearchBar", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders search input", () => {
    const { wrapper } = createWrapper();
    render(<AlphaSearchBar totalMatchCount={5} activeIndex={2} navigateToMatch={vi.fn()} />, { wrapper });
    expect(screen.getByTestId(ElementIds.CHAT_SEARCH_INPUT)).toBeInTheDocument();
  });

  it("renders match counter", () => {
    const { wrapper } = createWrapper();
    render(<AlphaSearchBar totalMatchCount={5} activeIndex={2} navigateToMatch={vi.fn()} />, { wrapper });
    expect(screen.getByTestId(ElementIds.CHAT_SEARCH_MATCH_COUNTER)).toBeInTheDocument();
  });

  it("renders search bar container", () => {
    const { wrapper } = createWrapper();
    render(<AlphaSearchBar totalMatchCount={0} activeIndex={0} navigateToMatch={vi.fn()} />, { wrapper });
    expect(screen.getByTestId(ElementIds.CHAT_SEARCH_BAR)).toBeInTheDocument();
  });

  it("calls navigateToMatch on Enter", async () => {
    const navigateToMatch = vi.fn();
    const { wrapper } = createWrapper();
    render(<AlphaSearchBar totalMatchCount={5} activeIndex={2} navigateToMatch={navigateToMatch} />, {
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
    render(<AlphaSearchBar totalMatchCount={5} activeIndex={2} navigateToMatch={navigateToMatch} />, {
      wrapper,
    });

    const input = screen.getByTestId(ElementIds.CHAT_SEARCH_INPUT);
    await userEvent.type(input, "test");
    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");

    expect(navigateToMatch).toHaveBeenCalledWith(1); // activeIndex - 1
  });
});
