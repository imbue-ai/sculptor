import { useAtomValue } from "jotai";
import { useEffect, useMemo, useRef } from "react";

import { formatShortcutForDisplay } from "~/common/keybindings/format.ts";
import { shouldHandleKeybinding } from "~/common/keybindings/matching.ts";
import { isDismissibleOverlayOpen } from "~/common/utils/overlays.ts";

import type { KeybindingId } from "./model.ts";
import { keybindingsMapAtom } from "./resolvedBindings.ts";

export const useKeybinding = (id: KeybindingId): string | null => {
  const map = useAtomValue(keybindingsMapAtom);
  return map[id].binding;
};

export const useKeybindingDisplayText = (id: KeybindingId): string => {
  const binding = useKeybinding(id);
  return useMemo(() => {
    if (binding == null) return "";
    return formatShortcutForDisplay(binding);
  }, [binding]);
};

export const useKeybindingHandler = (id: KeybindingId, handler: () => void): void => {
  const binding = useKeybinding(id);

  // Keep the latest handler in a ref so the keydown listener is registered only
  // when the binding changes, not on every render when `handler` is an inline function.
  // The ref is synced in an effect (not during render) so it satisfies the refs lint;
  // the listener only fires on real keypresses, well after commit, so a brief stale
  // window is harmless.
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    if (binding == null) return;

    const listener = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;
      if (shouldHandleKeybinding(e, binding)) {
        e.preventDefault();
        e.stopPropagation();
        handlerRef.current();
      }
    };

    window.addEventListener("keydown", listener);
    return (): void => window.removeEventListener("keydown", listener);
  }, [binding]);
};
