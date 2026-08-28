// Drives the active-section ring fade (visible for RING_VISIBLE_MS after each jump).
// The LOGICAL active sub-section persists; the ring VISIBILITY is transient and flashes
// only on a deliberate jump (keyboard cycle, add, drop, workspace entry), each of which
// bumps activeSectionRingNonceAtom via jumpToSectionAtom. On every bump this shows the
// ring and (re)starts a single RING_VISIBLE_MS timer that hides it; a fresh bump resets
// the timer so a rapid re-trigger keeps the ring up for the full window.
//
// Mounted ONCE at the shell level. Only activeSectionRingVisibleAtom flips here, and
// isRingVisibleAtom(ss) is per-sub-section (active AND visible), so just the active
// section re-renders for the fade — never the whole grid.

import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import {
  activeSectionRingNonceAtom,
  activeSectionRingVisibleAtom,
  RING_VISIBLE_MS,
} from "~/pages/workspace/layout/atoms/transient.ts";

export const useActiveSectionRing = (): void => {
  const nonce = useAtomValue(activeSectionRingNonceAtom);
  const setRingVisible = useSetAtom(activeSectionRingVisibleAtom);
  const lastNonceRef = useRef<number>(nonce);

  useEffect(() => {
    // Only a genuine nonce bump flashes: mounting the shell is not a jump. Keying on
    // the last-processed nonce is idempotent, so StrictMode's double effect invocation
    // (which preserves refs but re-runs effects) cannot flash on the initial mount.
    // Workspace entry pulses explicitly by bumping the nonce after mount.
    if (lastNonceRef.current === nonce) {
      return;
    }
    lastNonceRef.current = nonce;
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
};
