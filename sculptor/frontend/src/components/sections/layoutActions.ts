// Write-only action atoms for the saved-Layouts feature: apply / tidy / save /
// delete / set-default / rename. Each computes the next state through the pure
// reducers (layoutApply.ts, layoutCapture.ts) and writes it through the
// consolidated layout atoms — never localStorage directly.

import { atom } from "jotai";

import { applyCapturedLayout, computeTidyClosure } from "./layoutApply.ts";
import { captureLayout } from "./layoutCapture.ts";
import type { SavedLayout } from "./persistence/types.ts";
import { SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import {
  appliedLayoutIdAtom,
  defaultLayoutIdAtom,
  layoutMruAtom,
  savedLayoutsAtom,
  tidyConfirmationSuppressedAtom,
} from "./savedLayoutAtoms.ts";
import { closePanelAtom } from "./sectionActions.ts";
import { workspaceLayoutAtom } from "./sectionAtoms.ts";
import { isSystemLayoutId, SYSTEM_DEFAULT_LAYOUT_ID } from "./systemDefaultLayout.ts";
import { activeSectionRingNonceAtom, layoutTidyTargetAtom, maximizedSectionAtom } from "./transientAtoms.ts";

// Move an id to the front of the MRU list (most-recently-applied first),
// de-duplicating any earlier occurrence.
function withFront(ids: ReadonlyArray<string>, id: string): Array<string> {
  return [id, ...ids.filter((existing) => existing !== id)];
}

// Apply a Layout to the active workspace: additive arrangement + geometry +
// maximize, record it as the applied Layout, move it to the front of the MRU, and
// pulse the active-section ring (applying is a deliberate jump). If the Layout opts
// into tidy-on-apply, close the static panels it doesn't declare too: silently when
// the user has globally dismissed the confirmation, otherwise via the Tidy
// confirmation (which is itself a no-op when nothing would close). This is the single
// choke point every apply path routes through — switcher, command palette, and
// per-Layout shortcut — so the flags are honored consistently.
export const applyLayoutAtom = atom(null, (get, set, layout: SavedLayout) => {
  const result = applyCapturedLayout(get(workspaceLayoutAtom), layout.captured);
  set(workspaceLayoutAtom, { ...result.layout, appliedLayoutId: layout.id });
  set(maximizedSectionAtom, result.maximizedSection);
  set(layoutMruAtom, withFront(get(layoutMruAtom), layout.id));
  set(activeSectionRingNonceAtom, (nonce) => nonce + 1);
  if (layout.tidyOnApply === true) {
    if (get(tidyConfirmationSuppressedAtom)) {
      set(tidyToLayoutAtom, layout);
    } else {
      set(layoutTidyTargetAtom, layout);
    }
  }
});

// Close the static panels the given Layout does not declare (never agents/
// terminals). The caller confirms first when the closure is non-empty; a no-op
// closure applies silently.
export const tidyToLayoutAtom = atom(null, (get, set, layout: SavedLayout) => {
  for (const { panelId } of computeTidyClosure(get(workspaceLayoutAtom), layout.captured)) {
    set(closePanelAtom, { panelId });
  }
});

// Snapshot the active workspace's current arrangement as a new Layout (static-only,
// via captureLayout), record it as this workspace's applied Layout, and optionally
// make it the new-workspace default and opt it into tidy-on-apply. Returns the new
// Layout's id (so the caller can attach a keyboard shortcut to it).
export const saveCurrentLayoutAtom = atom(
  null,
  (get, set, params: { name: string; setAsDefault: boolean; tidyOnApply: boolean }): string => {
    const captured = captureLayout(get(workspaceLayoutAtom), get(maximizedSectionAtom));
    const id = crypto.randomUUID();
    const layout: SavedLayout = {
      id,
      name: params.name.trim(),
      captured,
      version: SAVED_LAYOUT_VERSION,
      tidyOnApply: params.tidyOnApply,
    };
    set(savedLayoutsAtom, [...get(savedLayoutsAtom), layout]);
    set(appliedLayoutIdAtom, id);
    set(layoutMruAtom, withFront(get(layoutMruAtom), id));
    if (params.setAsDefault) {
      set(defaultLayoutIdAtom, id);
    }
    return id;
  },
);

// Remove a Layout. Built-in layouts (System Default + presets) are undeletable. A
// default pointer at the deleted Layout falls back to System Default, and the active
// workspace drops a now-dangling applied pointer (other workspaces resolve theirs to
// "no Current" at read time).
export const deleteLayoutAtom = atom(null, (get, set, id: string) => {
  if (isSystemLayoutId(id)) {
    return;
  }
  set(
    savedLayoutsAtom,
    get(savedLayoutsAtom).filter((layout) => layout.id !== id),
  );
  set(
    layoutMruAtom,
    get(layoutMruAtom).filter((existing) => existing !== id),
  );
  if (get(defaultLayoutIdAtom) === id) {
    set(defaultLayoutIdAtom, SYSTEM_DEFAULT_LAYOUT_ID);
  }

  if (get(appliedLayoutIdAtom) === id) {
    set(appliedLayoutIdAtom, undefined);
  }
});

// Point the new-workspace default at a Layout.
export const setDefaultLayoutAtom = atom(null, (_get, set, id: string) => {
  set(defaultLayoutIdAtom, id);
});

// Update a Layout's editable metadata (name, tidy-on-apply, and whether it's the
// new-workspace default) from the Edit form — never the captured arrangement, which
// stays exactly as it was saved. Built-in layouts have no stored record, so they're
// ignored. An empty name is treated as "leave the name alone" rather than clearing
// it. `setAsDefault` owns the default pointer for THIS Layout only: turning it on
// points the default here, turning it off reverts to System Default only when this
// Layout currently holds it (so editing a non-default Layout never steals it).
export const updateLayoutAtom = atom(
  null,
  (get, set, params: { id: string; name: string; setAsDefault: boolean; tidyOnApply: boolean }) => {
    if (isSystemLayoutId(params.id)) {
      return;
    }
    const name = params.name.trim();
    set(
      savedLayoutsAtom,
      get(savedLayoutsAtom).map((layout) =>
        layout.id === params.id
          ? { ...layout, name: name === "" ? layout.name : name, tidyOnApply: params.tidyOnApply }
          : layout,
      ),
    );
    if (params.setAsDefault) {
      set(defaultLayoutIdAtom, params.id);
    } else if (get(defaultLayoutIdAtom) === params.id) {
      set(defaultLayoutIdAtom, SYSTEM_DEFAULT_LAYOUT_ID);
    }
  },
);
