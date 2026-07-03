/* eslint-disable react-hooks/immutability -- This hook imperatively restores
   scrolling: it deliberately writes the TanStack virtualizer's internals
   (scrollOffset, measureElement's caches via the settle sweep) so the restored
   position and window are coherent before the switch commit paints. These
   mutations are intentional and cannot be expressed within the compiler's
   immutability model — same pattern as useAlphaAutoScroll. */
import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom } from "jotai";
import type { RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

import { contentBottomOffset, distanceFromContentBottom, maxScrollOffset } from "../scroll/geometry.ts";
import type { ScrollStateMachine } from "../scroll/scrollStateMachine.ts";

/** Cancel all pending rAFs tracked in the set and clear it. */
const cancelPendingRafs = (ids: Set<number>): void => {
  for (const id of ids) cancelAnimationFrame(id);
  ids.clear();
};

const BOTTOM_THRESHOLD = 200;

type MessageRef = { id: string };

export const useAlphaScrollPersistence = (
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  taskId: string,
  filteredMessages: ReadonlyArray<MessageRef>,
  machine: ScrollStateMachine,
): void => {
  const [scrollPosition, setScrollPosition] = useAtom(alphaScrollPositionAtomFamily(taskId));
  const prevTaskIdRef = useRef(taskId);
  const pendingRafsRef = useRef(new Set<number>());

  // Save scroll position (rAF-debounced)
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    let rafId: number | null = null;

    const handleScroll = (): void => {
      // Don't record positions the restore itself produces — the machine is in
      // `restoring` for the whole restore window.
      if (machine.getState().authority.kind === "restoring") return;

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
        });
      });
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return (): void => {
      el.removeEventListener("scroll", handleScroll);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [scrollContainerRef, virtualizer, filteredMessages, setScrollPosition, machine]);

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

    if (scrollPosition.distanceFromBottom <= BOTTOM_THRESHOLD) {
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
  const pendingPrePaintApplyRef = useRef(false);

  // Synchronously measure every mounted row and hand the virtualizer the
  // restored offset, inside the switch commit (pre-paint).
  //
  // virtual-core's measureElement() resizes its item cache immediately, and
  // TanStack only learns a new scrollTop from the async scroll event —
  // pre-setting virtualizer.scrollOffset lets the settle render compute the
  // window at the *restored* offset instead of the outgoing task's. Per-item
  // scroll compensation is gated off for the whole `measuring` layout phase,
  // so none of these measurements can move scrollTop on their own.
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
    if (!pendingPrePaintApplyRef.current) return;
    pendingPrePaintApplyRef.current = false;
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

    // Cancel any in-flight rAFs from a previous restore call
    cancelPendingRafs(pendingRafsRef.current);
    // Enter `restoring` before any early return: a switch must never leave the
    // outgoing task's settled state visible on the container (a settled-wait
    // sampling that stale "true" races ahead of the incoming restore). The
    // machine owns "a restore is in flight", which suppresses position saves
    // and is reflected to the DOM as data-scroll-phase.
    machine.dispatch({ kind: "taskSwitched", taskId });
    if (!el || filteredMessages.length === 0) {
      // Nothing to restore — settle right back.
      machine.dispatch({ kind: "restoreSettled" });
      return;
    }

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
      pendingPrePaintApplyRef.current = true;
      setSettleRender((count) => count + 1);
    }

    // Safety-net re-assert after the virtualizer's settle window. The pre-paint
    // settle already applied against swept measurements, so this is normally a
    // no-op (writing an equal scrollTop fires no scroll event). It catches what
    // the sweep cannot: rows whose async re-measurement (images, fonts, late
    // reflows) lands after the settle render.
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
  }, [scrollContainerRef, filteredMessages, applyScrollPosition, sweepMountedMeasurements, machine, taskId]);

  // Restore scroll position synchronously before paint so the user never
  // sees the old scroll position flash before jumping to the saved one.
  useLayoutEffect(() => {
    if (prevTaskIdRef.current !== taskId) {
      prevTaskIdRef.current = taskId;

      restore();
    }
  }, [taskId, restore]);

  // Initial restore on mount; cancel pending rAFs on unmount
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- see the task-switch effect above
    restore();
    const rafs = pendingRafsRef.current;
    return (): void => cancelPendingRafs(rafs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
