// Hooks for reading/writing a Layout's keyboard shortcut and checking chord
// conflicts. Layout bindings live in userConfig.keybindings under the namespaced
// `layout.apply.<id>` key (see layoutShortcuts.ts); these wrap the userConfig
// update path so callers (the save dialog, the Settings ▸ Keybindings Layouts
// group, and the delete cleanup) never touch the raw dict directly.

import { useStore } from "jotai";
import { useCallback } from "react";

import { UserConfigField } from "~/api";
import { chordsEqual } from "~/common/ShortcutUtils.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { useUserConfig } from "~/common/state/hooks/useUserConfig.ts";

import { allNamedBindingsAtom, layoutShortcutBindingId, type NamedBinding } from "./layoutShortcuts.ts";

// Set (or, with null, clear) a Layout's shortcut. Clearing removes the key entirely
// rather than storing an explicit-null override, since layout bindings have no
// default to override — so the dict never accumulates dead entries.
export function useSetLayoutShortcut(): (layoutId: string, chord: string | null) => Promise<void> {
  const { updateField } = useUserConfig();
  const store = useStore();
  return useCallback(
    async (layoutId: string, chord: string | null): Promise<void> => {
      const next: Record<string, string | null> = { ...(store.get(userConfigAtom)?.keybindings ?? {}) };
      const key = layoutShortcutBindingId(layoutId);
      if (chord === null) {
        if (!(key in next)) {
          return;
        }
        delete next[key];
      } else {
        next[key] = chord;
      }
      await updateField(UserConfigField.KEYBINDINGS, next);
    },
    [updateField, store],
  );
}

// Find an existing binding (static or per-layout) that a recorded chord would
// collide with, ignoring the Layout currently being edited. Returns null when the
// chord is free. Spans both lanes via allNamedBindingsAtom so neither can silently
// shadow the other.
//
// Takes the LAYOUT id being edited (or undefined when creating a new Layout) and
// resolves the namespaced `layout.apply.<id>` binding id itself — callers hold a
// layout id, not a binding id, so resolving here removes the chance of passing the
// wrong shape and defeating the self-skip.
export function useLayoutBindingConflict(): (chord: string, selfLayoutId: string | undefined) => NamedBinding | null {
  const store = useStore();
  return useCallback(
    (chord: string, selfLayoutId: string | undefined): NamedBinding | null => {
      const selfBindingId = selfLayoutId !== undefined ? layoutShortcutBindingId(selfLayoutId) : null;
      for (const candidate of store.get(allNamedBindingsAtom)) {
        if (candidate.id === selfBindingId || candidate.binding === null) {
          continue;
        }

        if (chordsEqual(chord, candidate.binding)) {
          return candidate;
        }
      }
      return null;
    },
    [store],
  );
}
