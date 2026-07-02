// Drives the ~2-second active-section ring fade. The LOGICAL active
// sub-section persists; the ring VISIBILITY is transient and flashes only on a
// deliberate jump (keyboard cycle, add, drop, workspace entry), each of which bumps
// activeSectionRingNonceAtom via jumpToSectionAtom. On every bump this shows the ring
// and (re)starts a single RING_VISIBLE_MS timer that hides it; a fresh bump resets the
// timer so a rapid re-trigger keeps the ring up for the full window.
//
// Mounted ONCE at the shell level. Only activeSectionRingVisibleAtom flips here, and
// isRingVisibleAtom(ss) is per-sub-section (active AND visible), so just the active
// section re-renders for the fade — never the whole grid.

import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { activeSectionRingNonceAtom, activeSectionRingVisibleAtom, RING_VISIBLE_MS } from "./transientAtoms.ts";

export function useActiveSectionRing(): void {
  const nonce = useAtomValue(activeSectionRingNonceAtom);
  const setRingVisible = useSetAtom(activeSectionRingVisibleAtom);
  const hasMountedRef = useRef<boolean>(false);

  useEffect(() => {
    // The initial mount (nonce 0) must not flash: re-entering the shell is not a jump.
    // Workspace entry pulses explicitly by bumping the nonce after mount.
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return;
    }
    setRingVisible(true);
    const timer = setTimeout(() => setRingVisible(false), RING_VISIBLE_MS);
    return (): void => clearTimeout(timer);
  }, [nonce, setRingVisible]);

  // The visibility atom outlives this hook (it is app-global), so an unmount
  // mid-fade must reset it — otherwise the next shell mount would start with the
  // ring stuck visible until the next jump restarts the timer.
  useEffect(() => {
    return (): void => setRingVisible(false);
  }, [setRingVisible]);
}
