import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtom } from "jotai";
import type { RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

import { chatScrollPositionAtomFamily } from "~/common/state/atoms/chatScroll.ts";

import { contentBottomOffset, distanceFromContentBottom, maxScrollOffset } from "../scroll/geometry.ts";
import type { ScrollStateMachine } from "../scroll/scrollStateMachine.ts";

/** Cancel all pending rAFs tracked in the set and clear it. */
const cancelPendingRafs = (ids: Set<number>): void => {
  for (const id of ids) cancelAnimationFrame(id);
  ids.clear();
};

const BOTTOM_THRESHOLD = 200;

type MessageRef = { id: string };

export const useChatScrollPersistence = (
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  agentId: string,
  filteredMessages: ReadonlyArray<MessageRef>,
  machine: ScrollStateMachine,
): void => {
  const [scrollPosition, setScrollPosition] = useAtom(chatScrollPositionAtomFamily(agentId));
  const prevAgentIdRef = useRef(agentId);
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
  const applyScrollPosition = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return;

    if (!scrollPosition) {
      // First visit: land at the very end of the padded scroll range. For a
      // agent whose last turn is short, the dynamic paddingEnd makes this the
      // anchored-turn rest position (last user message at the viewport top) —
      // the view the agent's owner last saw.
      el.scrollTop = maxScrollOffset(el);
      return;
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

  // Restore scroll position on agent switch
  const restore = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el || filteredMessages.length === 0) return;

    // Cancel any in-flight rAFs from a previous restore call
    cancelPendingRafs(pendingRafsRef.current);
    // Enter `restoring`: the machine now owns "a restore is in flight", which
    // suppresses position saves and is reflected to the DOM as data-scroll-phase.
    machine.dispatch({ kind: "agentSwitched", agentId });

    // First apply: resolves the anchor against the virtualizer's *estimated*
    // heights — on an agent switch the virtualizer is mid-settle and the items
    // have not re-measured to their real sizes yet. This prevents a flash of
    // the outgoing scroll position.
    applyScrollPosition();

    // Re-assert after the virtualizer has settled. useChatVirtualizer's layout
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
  }, [scrollContainerRef, filteredMessages, applyScrollPosition, machine, agentId]);

  // Restore scroll position synchronously before paint so the user never
  // sees the old scroll position flash before jumping to the saved one.
  useLayoutEffect(() => {
    if (prevAgentIdRef.current !== agentId) {
      prevAgentIdRef.current = agentId;
      restore();
    }
  }, [agentId, restore]);

  // Initial restore on mount; cancel pending rAFs on unmount
  useEffect(() => {
    restore();
    const rafs = pendingRafsRef.current;
    return (): void => cancelPendingRafs(rafs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
