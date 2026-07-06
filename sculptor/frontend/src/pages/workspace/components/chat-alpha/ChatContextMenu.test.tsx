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

  it("does not overwrite the clipboard when Copy is selected with no text selected", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "" } as Selection);

    render(
      <ChatContextMenu>
        <div data-testid="content">chat text</div>
      </ChatContextMenu>,
      { wrapper: Wrapper },
    );

    fireEvent.contextMenu(screen.getByTestId("content"));
    const copyItem = await screen.findByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_COPY);
    fireEvent.click(copyItem);

    expect(writeText).not.toHaveBeenCalled();
  });

  it("dispatches a paste event containing the clipboard contents when Paste is selected", async () => {
    const readText = vi.fn().mockResolvedValue("pasted text");
    Object.defineProperty(navigator, "clipboard", {
      value: { readText },
      configurable: true,
    });

    const editor = document.createElement("div");
    Object.defineProperty(editor, "isContentEditable", { value: true });
    document.body.appendChild(editor);
    editor.focus();

    let receivedText = "";
    editor.addEventListener("paste", (e: ClipboardEvent) => {
      receivedText = e.clipboardData?.getData("text/plain") ?? "";
    });

    render(
      <ChatContextMenu>
        <div data-testid="content">chat text</div>
      </ChatContextMenu>,
      { wrapper: Wrapper },
    );

    fireEvent.contextMenu(screen.getByTestId("content"));
    const pasteItem = await screen.findByTestId(ElementIds.ALPHA_CHAT_CONTEXT_MENU_PASTE);
    // Selecting a Radix Menu.Item fires onSelect, then Radix calls e.preventDefault()
    // on the underlying click — fire directly through the onSelect handler by
    // dispatching contextmenu first and using fireEvent.click on the item.
    fireEvent.click(pasteItem);
    // Allow the async readText() handler to resolve.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(receivedText).toBe("pasted text");
    document.body.removeChild(editor);
  });
});
