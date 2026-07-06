import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import { ElementIds } from "~/api";

type ChatContextMenuProps = {
  children: ReactNode;
};

/** Right-click context menu for the chat content area. */
export const ChatContextMenu = ({ children }: ChatContextMenuProps): ReactElement => {
  const handleCopy = (): void => {
    void navigator.clipboard.writeText(window.getSelection()?.toString() ?? "");
  };

  const handlePaste = async (): Promise<void> => {
    const text = await navigator.clipboard.readText();
    if (!text) return;
    const activeElement = document.activeElement;
    if (activeElement && (activeElement as HTMLElement).isContentEditable) {
      const pasteEvent = new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: new DataTransfer(),
      });
      activeElement.dispatchEvent(pasteEvent);
    }
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
