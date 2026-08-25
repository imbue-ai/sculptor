// Transient (non-persisted) UI state for the Layouts surfaces: which dialog is
// open. Plain primitive atoms — they reset on reload, so a stale open flag can
// never strand a dialog. The hosts (mounted in AppShell) subscribe to these;
// entry points set them. (The pending-Tidy-target atom lives in sections/
// transientAtoms.ts, since the apply engine drives it.)

import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";

import type { SavedLayout } from "~/components/sections/persistence/types.ts";

export const layoutsSwitcherOpenAtom: PrimitiveAtom<boolean> = atom<boolean>(false);

// What the Save/Edit dialog is doing right now (null = closed). "create" snapshots
// the current workspace into a new Layout; "edit" reopens the same form on an
// existing Layout to change its name / shortcut / tidy / default without
// re-capturing its arrangement. One atom rather than an open flag + a separate
// target so the two can never disagree.
export type SaveLayoutModalRequest = { mode: "create" } | { mode: "edit"; layout: SavedLayout };

export const saveLayoutModalRequestAtom: PrimitiveAtom<SaveLayoutModalRequest | null> =
  atom<SaveLayoutModalRequest | null>(null);
