/* eslint-disable react-hooks/immutability -- This hook imperatively restores
   scrolling: it deliberately writes the TanStack virtualizer's internals
   (scrollOffset, measureElement's caches via the settle sweep) so the restored
   position and window are coherent before the switch commit paints. These
   mutations are intentional and cannot be expressed within the compiler's
   immutability model — same pattern as useAlphaAutoScroll. */
import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom } from "jotai";
import type { MutableRefObject, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

import {
  bottomThresholdFor,
  contentBottomOffset,
  distanceFromContentBottom,
  maxScrollOffset,
} from "../scroll/geometry.ts";
import type { ScrollStateMachine } from "../scroll/scrollStateMachine.ts";

/** Cancel all pending rAFs tracked in the set and clear it. */
const cancelPendingRafs = (ids: Set<number>): void => {
  for (const id of ids) cancelAnimationFrame(id);
  ids.clear();
};

/** A bottom-relative restore re-pins every animation frame while the mounted
 *  rows replace their cold estimates with real measurements (which grows the
 *  content height). Convergence is declared once the height holds steady for
 *  this many consecutive frames. */
const BOTTOM_CONVERGE_STABLE_FRAMES = 2;
/** Hard cap on the re-pin chase, so a task whose content never stabilizes for
 *  two consecutive frames (a live stream, a perpetually reflowing row) still
 *  hands control back. Real cold-estimate convergence is a handful of frames, so
 *  this only fires on genuinely never-settling content; kept tight (~0.5s at
 *  60fps) so `restoring` — which withholds `settled` and suppresses saves — is
 *  never held long past convergence. */
const BOTTOM_CONVERGE_MAX_FRAMES = 30;

type MessageRef = { id: string };

export const useAlphaScrollPersistence = (
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  taskId: string,
  filteredMessages: ReadonlyArray<MessageRef>,
  machine: ScrollStateMachine,
  isProgrammaticScrollRef: MutableRefObject<boolean>,
): void => {
  const [scrollPosition, setScrollPosition] = useAtom(alphaScrollPositionAtomFamily(taskId));
  const prevTaskIdRef = useRef(taskId);
  const pendingRafsRef = useRef(new Set<number>());
  // A restore that arrived before the task's messages did (cold task-detail
  // atom right after a switch). Held until the first non-empty message list.
  const pendingRestoreRef = useRef(false);

  // Save scroll position (rAF-debounced)
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    let rafId: number | null = null;

    const handleScroll = (): void => {
      // Don't record positions the restore itself produces — the machine is in
      // `restoring` for the whole restore window.
      if (machine.getState().authority.kind === "restoring") return;
      // Nor positions produced by other programmatic scrolls: pin-to-bottom
      // writes and TanStack's per-item scroll compensation flag themselves
      // here, and mid-measurement compensation in particular lands at
      // positions the user never chose — recording one overwrites the real
      // reading position. The flag is cleared in a microtask (after every
      // listener of this event has run), so this read is safe regardless of
      // listener registration order. Sampled at event time: the rAF below
      // runs after the microtask clear.
      if (isProgrammaticScrollRef.current) return;

      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const virtualItems = virtualizer.getVirtualItems();
        if (virtualItems.length === 0) return;

        const scrollTop = el.scrollTop;
        // Find first visible item
        const firstVisible = virtualItems.find((item) => item.start + item.size > scrollTop) ?? virtualItems[0];
        const messageIndex = firstVisible.index;
        if (messageIndex >= filteredMessages.length) return;

        const message = filteredMessages[messageIndex];
        setScrollPosition({
          firstVisibleMessageId: message.id,
          pixelOffset: scrollTop - firstVisible.start,
          // Signed distance to the real content bottom (paddingEnd excluded,
          // negative inside the tail padding). The restore re-lands at this
          // distance from the then-current content bottom, so an at-bottom
          // reader follows content that grew while away and a position inside
          // the padding (the anchored rest / a max scroll) round-trips.
          distanceFromBottom: distanceFromContentBottom(el, virtualizer),
          savedAtMs: Date.now(),
        });
      });
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return (): void => {
      el.removeEventListener("scroll", handleScroll);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [scrollContainerRef, virtualizer, filteredMessages, setScrollPosition, machine, isProgrammaticScrollRef]);

  // Apply the saved scroll position to the container. Resolves the saved anchor
  // (message index + pixel offset, or distance-from-bottom) against the
  // virtualizer's *current* item measurements, so calling it again after the
  // measurements change re-lands at the same logical position.
  const applyScrollPosition = useCallback((): "anchor" | "bottom" | "none" => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return "none";

    if (!scrollPosition) {
      // First visit: land at the very end of the padded scroll range. For a
      // task whose last turn is short, the dynamic paddingEnd makes this the
      // anchored-turn rest position (last user message at the viewport top) —
      // the view the task's owner last saw.
      el.scrollTop = maxScrollOffset(el);
      return "bottom";
    }

    if (scrollPosition.distanceFromBottom <= bottomThresholdFor(el)) {
      // At (or past) the bottom: re-land at the saved distance from the
      // *current* content bottom, not at the saved message anchor — when
      // content grew while away, an at-bottom reader should see the new
      // bottom. The distance is signed: negative means the viewport sat
      // inside the tail padding (a max scroll / the anchored rest), and
      // honoring it round-trips that position instead of clamping it flush
      // to the content. Clamp to the scrollable range, since paddingEnd may
      // have converged differently than when the distance was recorded.
      const target = contentBottomOffset(el, virtualizer) - scrollPosition.distanceFromBottom;
      el.scrollTop = Math.min(Math.max(0, target), maxScrollOffset(el));
      return "bottom";
    }

    const messageIndex = filteredMessages.findIndex((m) => m.id === scrollPosition.firstVisibleMessageId);
    const anchorItem = messageIndex >= 0 ? virtualizer.measurementsCache[messageIndex] : undefined;
    if (anchorItem) {
      // Resolve the anchor to an absolute scrollTop from the measurements
      // directly — NOT virtualizer.scrollToIndex. scrollToIndex arms TanStack's
      // scroll-reconcile loop, which keeps re-driving scrollTop toward the bare
      // item start for seconds afterwards, clobbering the pixel offset the
      // moment a measurement shifts. One absolute write has a single owner.
      const target = anchorItem.start + scrollPosition.pixelOffset;
      el.scrollTop = Math.min(Math.max(0, target), maxScrollOffset(el));
      return "anchor";
    } else {
      // Fallback: use distance from the content bottom. contentBottomOffset
      // excludes paddingEnd, matching how the distance was recorded above.
      el.scrollTop = contentBottomOffset(el, virtualizer) - scrollPosition.distanceFromBottom;
      return "bottom";
    }
  }, [scrollContainerRef, virtualizer, filteredMessages, scrollPosition]);

  // Forces the settle render from inside restore() so the pre-paint settle
  // effect below has a commit to run in.
  // eslint-disable-next-line react/hook-use-state -- value unused; only the setter triggers renders
  const [, setSettleRender] = useState(0);
  // Set while a restore has swept fresh measurements and the final pre-paint
  // apply is still owed; consumed by the settle layout effect below.
  const isPrePaintApplyPendingRef = useRef(false);

  // Synchronously measure every mounted row and hand the virtualizer the
  // restored offset, inside the switch commit (pre-paint).
  //
  // virtual-core's measureElement() resizes its item cache immediately, and
  // TanStack only learns a new scrollTop from the async scroll event —
  // pre-setting virtualizer.scrollOffset lets the settle render compute the
  // window at the *restored* offset instead of the outgoing task's. Per-item
  // scroll compensation is gated off for the whole `measuring` layout phase,
  // so none of these measurements can move scrollTop on their own. While
  // virtual-core still believes a scroll is in flight (~150ms after any scroll
  // event) measureElement declines to resize, so a switch right after a scroll
  // sweeps nothing — the settle then re-applies the estimate value and the
  // deferred safety net below carries the correction.
  const sweepMountedMeasurements = useCallback((): void => {
    const el = scrollContainerRef.current;
    if (!el) return;
    virtualizer.scrollOffset = el.scrollTop;
    el.querySelectorAll<HTMLElement>("[data-index]").forEach((node) => virtualizer.measureElement(node));
  }, [scrollContainerRef, virtualizer]);

  // The pre-paint settle: runs in the render restore() forces (a setState in a
  // layout effect commits synchronously before paint), after the target window
  // has mounted at the restored offset and its rows have self-measured via
  // their refs. The final apply therefore resolves against real geometry, and
  // the first painted frame of the incoming task is already the settled one —
  // no visible correction scroll afterwards. Declared before the task-switch
  // effect below so it consumes the flag in that forced render, not in the
  // same commit that set it.
  useLayoutEffect(() => {
    if (!isPrePaintApplyPendingRef.current) return;
    isPrePaintApplyPendingRef.current = false;
    const el = scrollContainerRef.current;
    if (!el) return;
    // Rebuild positions from the swept sizes and reflect the corrected total
    // height now — React re-applies the same value on its own next render.
    virtualizer.getVirtualItems();
    const content = el.firstElementChild as HTMLElement | null;
    if (content) {
      content.style.height = `${virtualizer.getTotalSize()}px`;
    }

    // Respect a user takeover during the restore window, mirroring the
    // deferred re-assert in restore().
    if (machine.getState().authority.kind === "restoring") {
      applyScrollPosition();
      virtualizer.scrollOffset = el.scrollTop;
    }
  });

  // Restore scroll position on task switch
  const restore = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    // Cancel any in-flight rAFs from a previous restore call
    cancelPendingRafs(pendingRafsRef.current);
    // Enter `restoring` before any early return: a switch must never leave the
    // outgoing task's settled state visible on the container (a settled-wait
    // sampling that stale "true" races ahead of the incoming restore). The
    // machine owns "a restore is in flight", which suppresses position saves
    // and is reflected to the DOM as data-scroll-phase.
    machine.dispatch({ kind: "taskSwitched", taskId });

    // The task's messages may not have arrived yet (the task-detail atom is
    // cold right after a switch and the unified stream fills it a beat later).
    // There is nothing to resolve the saved anchor against, so hold the
    // restore pending — the message-arrival effect below fires it on the first
    // non-empty list. Entering `restoring` above is what makes the wait safe:
    // the interim landing (content mounting, estimate-based pins) fires scroll
    // events that must not overwrite the saved position we have yet to read.
    if (filteredMessages.length === 0) {
      pendingRestoreRef.current = true;
      return;
    }
    pendingRestoreRef.current = false;

    // Force the measurements memo to rebuild before reading. The task-switch
    // wipe (useAlphaVirtualizer's layout effect, earlier in this commit) only
    // invalidates the size cache; the measurementsCache *field* still holds
    // the array computed during the render — the outgoing task's geometry.
    // Rebuilding here makes the first apply resolve against the incoming
    // task's cached estimates, and gives the sweep's partial rebuilds the
    // right baseline for every row below the mounted window.
    virtualizer.getVirtualItems();

    // First apply: resolves the anchor against the virtualizer's *estimated*
    // heights — the wipe on task switch means the items have not re-measured
    // to their real sizes yet. This lands close enough that the settle render
    // below computes the right window, and prevents a flash of the outgoing
    // scroll position.
    const resolution = applyScrollPosition();

    // Pre-paint settle, only for message-anchored restores: sweep real sizes
    // for the mounted rows, then force the render the settle effect above
    // consumes — it re-applies against the swept geometry before this commit
    // ever paints. Bottom-relative restores gain nothing from the sweep (their
    // target depends on the converged paddingEnd, which only the virtualizer's
    // own settle window produces), so they skip straight to the deferred
    // re-assert below rather than writing a mid-settle guess.
    if (resolution === "anchor") {
      sweepMountedMeasurements();
      isPrePaintApplyPendingRef.current = true;
      setSettleRender((count) => count + 1);
    }

    // Anchor restores land in one shot: the pre-paint sweep already resolved the
    // anchor against swept measurements, so a single deferred re-assert after
    // the virtualizer's settle window is enough to catch what the sweep cannot —
    // rows whose async re-measurement (images, fonts, late reflows) lands after
    // the settle render. Writing an equal scrollTop fires no scroll event, so
    // this is normally a no-op.
    if (resolution === "anchor") {
      const id1 = requestAnimationFrame(() => {
        pendingRafsRef.current.delete(id1);
        const id2 = requestAnimationFrame(() => {
          pendingRafsRef.current.delete(id2);
          // Only re-assert while the machine is still `restoring`. A genuine user
          // scroll during the restore window flips authority to `userControlled`
          // (see useScrollStateMachine), so this skips the re-assert rather than
          // snapping the view back to the saved anchor and clobbering them.
          if (machine.getState().authority.kind === "restoring") {
            applyScrollPosition();
          }
          // Settle: returns authority to `userControlled` (a no-op if the user
          // already took over).
          machine.dispatch({ kind: "restoreSettled" });
        });
        pendingRafsRef.current.add(id2);
      });
      pendingRafsRef.current.add(id1);
      return;
    }

    // Bottom-relative restores cannot settle in one shot. Their target is the
    // *content bottom*, which only exists once the mounted rows have replaced
    // their cold estimates with measured heights — a convergence that unfolds
    // over several frames (and, on a cold app start, while the rows are still
    // streaming in). A single deferred re-assert fires mid-convergence and
    // strands the reader pages above the true bottom, because the content keeps
    // growing after it settles. So re-pin every frame, re-resolving the bottom
    // against the now-current geometry, until the content height holds steady
    // for BOTTOM_CONVERGE_STABLE_FRAMES frames (converged) or the frame cap
    // elapses (never-settling content) — then hand control back. A genuine user
    // scroll flips authority out of `restoring` and ends the chase on the next
    // frame with no final clobbering write. Saves stay suppressed throughout:
    // the save handler ignores scrolls while authority is `restoring`.
    //
    // Each re-pin is a programmatic scrollTop write, so the loop holds
    // `isProgrammaticScrollRef` for the whole chase — the documented flag every
    // chat scroll listener reads to tell a restore from a user scroll (like
    // useAlphaAutoScroll's pinToBottom) — and clears it at every exit, so a
    // scroll event from a re-pin is never misread and the flag never lingers
    // past the restore.
    let lastHeight = el.scrollHeight;
    let stableFrames = 0;
    let elapsedFrames = 0;
    let rafId = 0;
    const endConvergence = (): void => {
      isProgrammaticScrollRef.current = false;
    };

    const tick = (): void => {
      pendingRafsRef.current.delete(rafId);
      const container = scrollContainerRef.current;
      // The user grabbed the scroll (or the container unmounted): stop chasing
      // and leave their position untouched. Authority is already userControlled.
      if (!container || machine.getState().authority.kind !== "restoring") {
        endConvergence();
        return;
      }

      isProgrammaticScrollRef.current = true;
      applyScrollPosition();

      const height = container.scrollHeight;
      stableFrames = height === lastHeight ? stableFrames + 1 : 0;
      lastHeight = height;
      elapsedFrames += 1;

      if (stableFrames >= BOTTOM_CONVERGE_STABLE_FRAMES || elapsedFrames >= BOTTOM_CONVERGE_MAX_FRAMES) {
        machine.dispatch({ kind: "restoreSettled" });
        endConvergence();
        return;
      }
      rafId = requestAnimationFrame(tick);
      pendingRafsRef.current.add(rafId);
    };
    rafId = requestAnimationFrame(tick);
    pendingRafsRef.current.add(rafId);
  }, [
    scrollContainerRef,
    virtualizer,
    filteredMessages,
    applyScrollPosition,
    sweepMountedMeasurements,
    machine,
    taskId,
    isProgrammaticScrollRef,
  ]);

  // Restore scroll position synchronously before paint so the user never
  // sees the old scroll position flash before jumping to the saved one.
  useLayoutEffect(() => {
    if (prevTaskIdRef.current !== taskId) {
      prevTaskIdRef.current = taskId;
      restore();
    }
  }, [taskId, restore]);

  // Fire a pending restore the moment the task's messages arrive. Pre-paint
  // for the same reason as the restores above. Skipped (and cleared) if the
  // user already scrolled during the wait: their position wins over the saved
  // one, exactly like the settled restore's re-assert courtesy.
  useLayoutEffect(() => {
    if (!pendingRestoreRef.current || filteredMessages.length === 0) return;
    pendingRestoreRef.current = false;
    if (machine.getState().authority.kind === "restoring") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore() forces the pre-paint settle render (see the settle layout effect above); the cascade is the mechanism, not an accident
      restore();
    }
  }, [filteredMessages, machine, restore]);

  // Initial restore on mount; cancel pending rAFs on unmount. A layout effect
  // for the same reason as the task-switch restore above: on mobile every
  // navigation REMOUNTS the chat, and a post-paint restore would flash the
  // pin-to-bottom position (painted by useAlphaAutoScroll's mount effects)
  // before jumping to the saved one. Running after that pin in the same
  // layout-effect queue (this hook is called later), the restore wins pre-paint.
  useLayoutEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- restore() forces the pre-paint settle render (see the settle layout effect above); the cascade is the mechanism, not an accident
    restore();
    const rafs = pendingRafsRef.current;
    return (): void => cancelPendingRafs(rafs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
