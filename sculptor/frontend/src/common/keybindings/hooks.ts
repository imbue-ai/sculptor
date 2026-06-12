import { useAtomValue } from "jotai";
import { useCallback, useEffect, useMemo } from "react";

import { formatShortcutForDisplay, isDismissibleOverlayOpen, shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";

import { keybindingsMapAtom } from "./atoms.ts";
import type { KeybindingId } from "./types.ts";

export function useKeybinding(id: KeybindingId): string | null {
  const map = useAtomValue(keybindingsMapAtom);
  return map[id].binding;
}

export function useKeybindingDisplayText(id: KeybindingId): string {
  const binding = useKeybinding(id);
  return useMemo(() => {
    if (binding == null) return "";
    return formatShortcutForDisplay(binding);
  }, [binding]);
}

export function useKeybindingHandler(id: KeybindingId, handler: () => void): void {
  const binding = useKeybinding(id);

  const stableHandler = useCallback(handler, [handler]);

  useEffect(() => {
    if (binding == null) return;

    const listener = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;
      if (shouldHandleKeybinding(e, binding)) {
        e.preventDefault();
        e.stopPropagation();
        stableHandler();
      }
    };

    window.addEventListener("keydown", listener);
    return (): void => window.removeEventListener("keydown", listener);
  }, [binding, stableHandler]);
}
