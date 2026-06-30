import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom } from "jotai";
import type { RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

import { contentBottomOffset, distanceFromContentBottom } from "../scroll/geometry.ts";
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
          // Distance to the real content bottom (paddingEnd excluded), so a user
          // pinned at the bottom while the virtualizer is padded still restores
          // to the bottom rather than into the empty tail padding.
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
  const applyScrollPosition = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return;

    if (!scrollPosition || scrollPosition.distanceFromBottom <= BOTTOM_THRESHOLD) {
      // First visit or user was at bottom: restore to the content bottom (flush),
      // not scrollToIndex(last, {align:"end"}) — that lands in the empty tail
      // padding (see contentBottomOffset), leaving the last line floating a
      // paddingEnd-tall gap above the viewport bottom after a task switch.
      el.scrollTop = contentBottomOffset(el, virtualizer);
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
    if (!el || filteredMessages.length === 0) return;

    // Cancel any in-flight rAFs from a previous restore call
    cancelPendingRafs(pendingRafsRef.current);
    // Enter `restoring`: the machine now owns "a restore is in flight", which
    // suppresses position saves and is reflected to the DOM as data-scroll-phase.
    machine.dispatch({ kind: "taskSwitched", taskId });

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

  // Initial restore on mount; cancel pending rAFs on unmount
  useEffect(() => {
    restore();
    const rafs = pendingRafsRef.current;
    return (): void => cancelPendingRafs(rafs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
