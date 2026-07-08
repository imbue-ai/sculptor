// Transient (non-persisted) UI state for the Layouts surfaces: which dialog is
// open, and the target of a pending Tidy confirmation. Plain primitive atoms —
// they reset on reload, so a stale open flag can never strand a dialog. The
// hosts (mounted in AppShell) subscribe to these; entry points set them.

import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";

import type { SavedLayout } from "~/components/sections/persistence/types.ts";

export const layoutsSwitcherOpenAtom: PrimitiveAtom<boolean> = atom<boolean>(false);

export const saveLayoutModalOpenAtom: PrimitiveAtom<boolean> = atom<boolean>(false);

// The layout a pending "Apply & tidy" confirmation is scoped to; null = none open.
export const layoutTidyTargetAtom: PrimitiveAtom<SavedLayout | null> = atom<SavedLayout | null>(null);
