import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom } from "jotai";
import type { MutableRefObject, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

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
  const applyScrollPosition = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return;

    if (!scrollPosition) {
      // First visit: land at the very end of the padded scroll range. For a
      // task whose last turn is short, the dynamic paddingEnd makes this the
      // anchored-turn rest position (last user message at the viewport top) —
      // the view the task's owner last saw.
      el.scrollTop = maxScrollOffset(el);
      return;
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
      return;
    }

    const messageIndex = filteredMessages.findIndex((m) => m.id === scrollPosition.firstVisibleMessageId);
    if (messageIndex >= 0) {
      virtualizer.scrollToIndex(messageIndex, { align: "start" });
      // Apply pixel offset synchronously — scrollToIndex already set scrollTop
      // so the DOM measurement is available. A rAF here would cause a one-frame
      // flash at the message-top position before the offset is applied.
      el.scrollTop += scrollPosition.pixelOffset;
    } else {
      // Fallback: use distance from the content bottom (synchronous for the same
      // reason). contentBottomOffset excludes paddingEnd, matching how the
      // distance was recorded above.
      el.scrollTop = contentBottomOffset(el, virtualizer) - scrollPosition.distanceFromBottom;
    }
  }, [scrollContainerRef, virtualizer, filteredMessages, scrollPosition]);

  // Restore scroll position on task switch
  const restore = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    // Cancel any in-flight rAFs from a previous restore call
    cancelPendingRafs(pendingRafsRef.current);
    // Enter `restoring`: the machine now owns "a restore is in flight", which
    // suppresses position saves and is reflected to the DOM as data-scroll-phase.
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

    // First apply: resolves the anchor against the virtualizer's *estimated*
    // heights — on a task switch the virtualizer is mid-settle and the items
    // have not re-measured to their real sizes yet. This prevents a flash of
    // the outgoing scroll position.
    applyScrollPosition();

    // Re-assert after the virtualizer has settled. useAlphaVirtualizer's layout
    // effect runs before this hook's (by call order) and schedules its settle
    // double-rAF first, so this double-rAF's inner frame fires after it: by then
    // the visible items have re-measured to their real heights. Re-applying
    // re-resolves the anchor against those measurements, so the target message
    // lands where intended instead of being left at a stale estimate-based pixel
    // — which, in a virtualized list, can scroll the target out of the rendered
    // window entirely.
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
  }, [scrollContainerRef, filteredMessages, applyScrollPosition, machine, taskId]);

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
    restore();
    const rafs = pendingRafsRef.current;
    return (): void => cancelPendingRafs(rafs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
