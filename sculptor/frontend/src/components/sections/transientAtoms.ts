// Transient (non-persisted) layout atoms — reset on reload, never go through the
// persistence adapter. Task 1.5 adds the maximized-section, drag-preview, and
// ring-visibility atoms here; this file starts with the ring nonce that the
// jumpToSection action (Task 1.4) bumps to restart the active-section ring fade.

import { atom } from "jotai";

// Bumped on a deliberate jump (keyboard cycle / add / drop / workspace entry) to
// (re)start the ~2s active-section ring fade timer. See RING_VISIBLE_MS in Task 1.5.
export const activeSectionRingNonceAtom = atom<number>(0);
