import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { ChatContextMenu } from "./ChatContextMenu";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChatContextMenu", () => {
  it("renders its children and does not show the menu until right-click", () => {
    render(
      <ChatContextMenu>
        <div data-testid="content">chat text</div>
      </ChatContextMenu>,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("content")).toBeInTheDocument();
    expect(screen.queryByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_COPY)).not.toBeInTheDocument();
  });

  it("shows Copy, Paste, and Select All items on right-click", async () => {
    render(
      <ChatContextMenu>
        <div data-testid="content">chat text</div>
      </ChatContextMenu>,
      { wrapper: Wrapper },
    );

    fireEvent.contextMenu(screen.getByTestId("content"));

    expect(await screen.findByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_COPY)).toHaveTextContent("Copy");
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_PASTE)).toHaveTextContent("Paste");
    expect(screen.getByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_SELECT_ALL)).toHaveTextContent("Select All");
  });

  it("copies the current selection to the clipboard when Copy is selected", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "selected text" } as Selection);

    render(
      <ChatContextMenu>
        <div data-testid="content">chat text</div>
      </ChatContextMenu>,
      { wrapper: Wrapper },
    );

    fireEvent.contextMenu(screen.getByTestId("content"));
    const copyItem = await screen.findByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_COPY);
    fireEvent.click(copyItem);

    expect(writeText).toHaveBeenCalledWith("selected text");
  });
});
