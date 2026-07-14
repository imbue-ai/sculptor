// Transient (non-persisted) UI state for the Layouts surfaces: which dialog is
// open. Plain primitive atoms — they reset on reload, so a stale open flag can
// never strand a dialog. The hosts (mounted in AppShell) subscribe to these;
// entry points set them. (The pending-Tidy-target atom lives in sections/
// transientAtoms.ts, since the apply engine drives it.)

import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";

export const layoutsSwitcherOpenAtom: PrimitiveAtom<boolean> = atom<boolean>(false);

export const saveLayoutModalOpenAtom: PrimitiveAtom<boolean> = atom<boolean>(false);
