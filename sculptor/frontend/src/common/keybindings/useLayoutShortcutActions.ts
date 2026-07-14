// Hooks for reading/writing a Layout's keyboard shortcut and checking chord
// conflicts. Layout bindings live in userConfig.keybindings under the namespaced
// `layout.apply.<id>` key (see layoutShortcuts.ts); these wrap the userConfig
// update path so callers (the save dialog, the Settings ▸ Keybindings Layouts
// group, and the delete cleanup) never touch the raw dict directly.

import { useStore } from "jotai";
import { useCallback } from "react";

import { UserConfigField } from "~/api";
import { parseShortcut } from "~/common/ShortcutUtils.ts";
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

function sameChord(a: string, b: string): boolean {
  const pa = parseShortcut(a);
  const pb = parseShortcut(b);
  return pa.meta === pb.meta && pa.ctrl === pb.ctrl && pa.alt === pb.alt && pa.shift === pb.shift && pa.key === pb.key;
}

// Find an existing binding (static or per-layout) that a recorded chord would
// collide with, ignoring the binding being edited. Returns null when the chord is
// free. Spans both lanes via allNamedBindingsAtom so neither can silently shadow the
// other.
export function useLayoutBindingConflict(): (chord: string, selfBindingId: string) => NamedBinding | null {
  const store = useStore();
  return useCallback(
    (chord: string, selfBindingId: string): NamedBinding | null => {
      for (const candidate of store.get(allNamedBindingsAtom)) {
        if (candidate.id === selfBindingId || candidate.binding === null) {
          continue;
        }

        if (sameChord(chord, candidate.binding)) {
          return candidate;
        }
      }
      return null;
    },
    [store],
  );
}
