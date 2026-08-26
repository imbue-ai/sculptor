// Jotai slices over the persisted stores for the saved-Layouts feature, following
// the sidebarAtoms.ts slice pattern: each is a narrow read/write view of one field
// so components subscribe to exactly what they need and every write goes through
// the consolidated persist path (never localStorage directly).
//
// The user's layouts + the default pointer + the MRU list live in the GLOBAL store
// (shared across workspaces). The applied-layout pointer is PER-WORKSPACE. The
// mutating actions (apply / save / delete / set-default / rename) live in
// layoutActions.ts; these are the plumbing they build on.

import type { Atom, WritableAtom } from "jotai";
import { atom } from "jotai";

import type { SavedLayout } from "./persistence/types.ts";
import { SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { globalLayoutAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID, SYSTEM_LAYOUTS } from "./systemDefaultLayout.ts";

// The user's saved layouts (excludes System Default, which is synthesized). Defaults
// to [] for global snapshots persisted before the field existed.
export const savedLayoutsAtom: WritableAtom<ReadonlyArray<SavedLayout>, [ReadonlyArray<SavedLayout>], void> = atom(
  (get) => get(globalLayoutAtom).savedLayouts ?? [],
  (_get, set, next: ReadonlyArray<SavedLayout>) => set(globalLayoutAtom, (prev) => ({ ...prev, savedLayouts: next })),
);

// The default-layout pointer, resolved to System Default when unset. Writing this
// only stores the id; deletion cleanup lives in the delete action.
export const defaultLayoutIdAtom: WritableAtom<string, [string], void> = atom(
  (get) => get(globalLayoutAtom).defaultLayoutId ?? SYSTEM_DEFAULT_LAYOUT_ID,
  (_get, set, id: string) => set(globalLayoutAtom, (prev) => ({ ...prev, defaultLayoutId: id })),
);

// Layout ids in most-recently-applied order (front = most recent), across all
// workspaces. Orders the switcher list (PyCharm ⌘E semantics).
export const layoutMruAtom: WritableAtom<ReadonlyArray<string>, [ReadonlyArray<string>], void> = atom(
  (get) => get(globalLayoutAtom).layoutMru ?? [],
  (_get, set, next: ReadonlyArray<string>) => set(globalLayoutAtom, (prev) => ({ ...prev, layoutMru: next })),
);

// Global "skip the tidy confirmation" preference. When true, applying a tidy-on
// layout closes the undeclared panels silently for EVERY layout. Set from the "Don't
// show this again" checkbox in the confirmation.
export const tidyConfirmationSuppressedAtom: WritableAtom<boolean, [boolean], void> = atom(
  (get) => get(globalLayoutAtom).tidyConfirmationSuppressed ?? false,
  (_get, set, next: boolean) => set(globalLayoutAtom, (prev) => ({ ...prev, tidyConfirmationSuppressed: next })),
);

// The layout last applied to the ACTIVE workspace (a detached-copy pointer). Marks
// the switcher's "Current" row and backs the light dirty check.
export const appliedLayoutIdAtom: WritableAtom<string | undefined, [string | undefined], void> = atom(
  (get) => get(workspaceLayoutAtom).appliedLayoutId,
  (_get, set, id: string | undefined) => set(workspaceLayoutAtom, (prev) => ({ ...prev, appliedLayoutId: id })),
);

// All selectable layouts: the built-in system layouts (System Default + task presets)
// first, then the user's saved layouts, skipping any whose captured version this build
// can't read. The switcher's full candidate set before MRU ordering / filtering.
export const resolvedLayoutsAtom: Atom<ReadonlyArray<SavedLayout>> = atom((get) => {
  const saved = get(savedLayoutsAtom).filter((layout) => layout.version === SAVED_LAYOUT_VERSION);
  return [...SYSTEM_LAYOUTS, ...saved];
});

// The resolved default layout: the one `defaultLayoutId` points at, falling back to
// System Default when the pointer is unset or names a since-deleted layout. This is
// what new workspaces seed from and what "switch to default" applies.
export const defaultLayoutAtom: Atom<SavedLayout> = atom((get) => {
  const id = get(defaultLayoutIdAtom);
  return get(resolvedLayoutsAtom).find((layout) => layout.id === id) ?? SYSTEM_DEFAULT_LAYOUT;
});
