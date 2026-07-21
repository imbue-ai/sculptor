// Runtime dispatcher for per-Layout keyboard shortcuts. The static keybindings flow
// through the registry-backed useKeybindingHandler (keyed by the closed KeybindingId
// union); per-Layout bindings are dynamic string ids, so they get this dedicated
// listener instead. Mounted once by WorkspaceLayoutShell (workspace pages only —
// applying a Layout needs an active workspace), mirroring useWorkspaceShortcuts.
//
// Reads bindings + layouts live from the store at press time (single subscription,
// no stale closures), guards against firing under a dismissible overlay, and applies
// the matched Layout through applyLayoutAtom — the same choke point every other apply
// path uses, so tidy-on-apply and MRU tracking are honored here too.

import { useStore } from "jotai";
import { useEffect } from "react";

import { layoutShortcutBindingsAtom } from "~/common/keybindings/layoutShortcuts.ts";
import { isDismissibleOverlayOpen } from "~/common/overlayUtils.ts";
import { shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";

import { applyLayoutAtom } from "./layoutActions.ts";
import { resolvedLayoutsAtom } from "./savedLayoutAtoms.ts";

export function useLayoutShortcutDispatcher(): void {
  const store = useStore();
  useEffect(() => {
    const handler = (event: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) {
        return;
      }
      const bindings = store.get(layoutShortcutBindingsAtom);
      for (const [layoutId, chord] of Object.entries(bindings)) {
        if (!shouldHandleKeybinding(event, chord)) {
          continue;
        }
        const layout = store.get(resolvedLayoutsAtom).find((candidate) => candidate.id === layoutId);
        if (layout === undefined) {
          continue;
        }
        event.preventDefault();
        event.stopPropagation();
        store.set(applyLayoutAtom, layout);
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return (): void => window.removeEventListener("keydown", handler);
  }, [store]);
}
