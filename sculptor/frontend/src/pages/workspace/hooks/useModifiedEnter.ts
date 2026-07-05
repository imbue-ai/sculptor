import { useCallback } from "react";

import { shouldHandleKeybinding } from "~/common/keybindings/matching.ts";
import { isModifierPressed } from "~/electron/utils.ts";

type UseModifiedEnterOptions = {
  onConfirm: () => void;
  onInterruptAndSend?: () => void;
  sendMessageBinding: string | null;
};

export const useModifiedEnter = ({
  onConfirm,
  onInterruptAndSend,
  sendMessageBinding,
}: UseModifiedEnterOptions): ((e: KeyboardEvent) => boolean) => {
  return useCallback(
    (e: KeyboardEvent): boolean => {
      if (e.key !== "Enter" || sendMessageBinding == null) {
        return false;
      }

      // Cmd+Shift+Enter (or Ctrl+Shift+Enter) always triggers interrupt-and-send
      if (e.shiftKey && isModifierPressed(e) && onInterruptAndSend) {
        onInterruptAndSend();
        return true;
      }

      // Check if the binding matches the event
      if (shouldHandleKeybinding(e, sendMessageBinding)) {
        onConfirm();
        return true;
      }

      return false;
    },
    [onConfirm, onInterruptAndSend, sendMessageBinding],
  );
};
