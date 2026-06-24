import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom } from "jotai";
import type { RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

import { alphaScrollPositionAtomFamily } from "~/common/state/atoms/alphaScroll.ts";

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
): void => {
  const [scrollPosition, setScrollPosition] = useAtom(alphaScrollPositionAtomFamily(taskId));
  const isRestoringRef = useRef(false);
  const prevTaskIdRef = useRef(taskId);
  const pendingRafsRef = useRef(new Set<number>());

  // Save scroll position (rAF-debounced)
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    let rafId: number | null = null;

    const handleScroll = (): void => {
      if (isRestoringRef.current) return;

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
          distanceFromBottom: el.scrollHeight - scrollTop - el.clientHeight,
        });
      });
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return (): void => {
      el.removeEventListener("scroll", handleScroll);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [scrollContainerRef, virtualizer, filteredMessages, setScrollPosition]);

  // Apply the saved scroll position to the container. Resolves the saved anchor
  // (message index + pixel offset, or distance-from-bottom) against the
  // virtualizer's *current* item measurements, so calling it again after the
  // measurements change re-lands at the same logical position.
  const applyScrollPosition = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return;

    if (!scrollPosition || scrollPosition.distanceFromBottom <= BOTTOM_THRESHOLD) {
      // First visit or user was at bottom: scroll to bottom.
      virtualizer.scrollToIndex(filteredMessages.length - 1, { align: "end" });
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
      // Fallback: use distance from bottom (synchronous for the same reason).
      el.scrollTop = el.scrollHeight - el.clientHeight - scrollPosition.distanceFromBottom;
    }
  }, [scrollContainerRef, virtualizer, filteredMessages, scrollPosition]);

  // Restore scroll position on task switch
  const restore = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return;

    // Cancel any in-flight rAFs from a previous restore call
    cancelPendingRafs(pendingRafsRef.current);
    isRestoringRef.current = true;

    // First apply: resolves the anchor against the virtualizer's *estimated*
    // heights — on a task switch the virtualizer is mid-settle and the items
    // have not re-measured to their real sizes yet. This prevents a flash of
    // the outgoing scroll position.
    applyScrollPosition();

    // Re-assert after the virtualizer has settled. useAlphaVirtualizer's layout
    // effect runs before this hook's (by call order) and schedules its settle
    // double-rAF first, so this double-rAF's inner frame fires after it: by then
    // `isSettlingRef` has cleared and the visible items have re-measured to
    // their real heights. Re-applying re-resolves the anchor against those
    // measurements, so the target message lands where intended instead of being
    // left at a stale estimate-based pixel — which, in a virtualized list, can
    // scroll the target out of the rendered window entirely (the flake this
    // fixes). isRestoringRef stays true across the whole window so this
    // re-assert's scroll events aren't saved back as a new position.
    const id1 = requestAnimationFrame(() => {
      pendingRafsRef.current.delete(id1);
      const id2 = requestAnimationFrame(() => {
        pendingRafsRef.current.delete(id2);
        applyScrollPosition();
        isRestoringRef.current = false;
      });
      pendingRafsRef.current.add(id2);
    });
    pendingRafsRef.current.add(id1);
  }, [scrollContainerRef, filteredMessages, applyScrollPosition]);

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
