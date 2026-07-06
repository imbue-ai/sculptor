import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import { ElementIds } from "~/api";
import { CHAT_INPUT_ELEMENT_ID } from "~/common/Constants";

type ChatContextMenuProps = {
  children: ReactNode;
};

/** Right-click context menu for the chat content area. */
export const ChatContextMenu = ({ children }: ChatContextMenuProps): ReactElement => {
  const handleCopy = (): void => {
    const selectionText = window.getSelection()?.toString();
    if (!selectionText) return;
    void navigator.clipboard.writeText(selectionText);
  };

  const handlePaste = async (): Promise<void> => {
    let text: string;
    try {
      text = await navigator.clipboard.readText();
    } catch (error) {
      // Clipboard permission denied (or not available); silently ignore
      // rather than surface an unhandled rejection for a user action.
      console.error("Failed to read clipboard:", error);
      return;
    }
    if (!text) return;
    // Always target the chat input — `findContentEditable` scanned the
    // entire DOM and could dispatch to an unrelated editor.
    const target = document.getElementById(CHAT_INPUT_ELEMENT_ID);
    if (!(target instanceof HTMLElement) || !target) return;
    const dataTransfer = new DataTransfer();
    dataTransfer.setData("text/plain", text);
    target.dispatchEvent(
      new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: dataTransfer,
      }),
    );
  };

  const handleSelectAll = (): void => {
    const selection = window.getSelection();
    if (!selection) return;
    const chatContainer = document.querySelector('[data-testid="' + ElementIds.ALPHA_CHAT_VIEW + '"]');
    if (chatContainer) {
      const range = document.createRange();
      range.selectNodeContents(chatContainer);
      selection.removeAllRanges();
      selection.addRange(range);
    }
  };

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        <ContextMenu.Item onSelect={handleCopy} data-testid={ElementIds.ALPHA_CHAT_CONTEXT_MENU_COPY}>
          Copy
        </ContextMenu.Item>
        <ContextMenu.Item onSelect={handlePaste} data-testid={ElementIds.ALPHA_CHAT_CONTEXT_MENU_PASTE}>
          Paste
        </ContextMenu.Item>
        <ContextMenu.Separator />
        <ContextMenu.Item onSelect={handleSelectAll} data-testid={ElementIds.ALPHA_CHAT_CONTEXT_MENU_SELECT_ALL}>
          Select All
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
