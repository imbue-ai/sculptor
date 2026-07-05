import type { VirtualItem, Virtualizer } from "@tanstack/react-virtual";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { MutableRefObject, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ChatMessageRole } from "~/api";

import { FOOTER_REVEAL_WINDOW_MS, IDLE_TAIL_PADDING, STREAMING_TAIL_PADDING } from "../scroll/geometry.ts";
import type { ScrollStateMachine } from "../scroll/scrollStateMachine.ts";

const ESTIMATED_MESSAGE_HEIGHT = 120;
const OVERSCAN = 5;

/**
 * Maximum number of agents whose per-item heights and tail content heights
 * are kept in the LRU cache.  When the cap is exceeded the least-recently
 * used entry is evicted.  This bounds memory usage for users who cycle
 * through many agent tabs without closing them.
 */
const MAX_CACHED_AGENTS = 20;

/**
 * Vertical padding above the virtualised list.
 *
 * Using `paddingStart` (and `paddingEnd` below) is the correct TanStack Virtual
 * way to reserve space – CSS padding on the container div is ignored by
 * absolutely-positioned virtual items.
 *
 * paddingStart matches var(--space-9) so the first message sits at the same
 * vertical position as subsequent user messages (which get a margin-top of
 * var(--space-9) via the .newCycle class). The paddingEnd floor is the
 * streaming-scoped IDLE_TAIL_PADDING / STREAMING_TAIL_PADDING pair — see the
 * dynamicPaddingEnd derivation below.
 */
const VIRTUAL_PADDING = 64;

/**
 * Touch `key` in a Map so it becomes the most-recently-used entry, then
 * evict the oldest entry if the map exceeds `maxSize`.  Map iteration
 * order is insertion order, so deleting and re-inserting moves the key
 * to the end.
 */
export const touchLRU = <TK, TV>(map: Map<TK, TV>, key: TK, maxSize: number): void => {
  const value = map.get(key);
  if (value !== undefined) {
    map.delete(key);
    map.set(key, value);
  }

  if (map.size > maxSize) {
    // Delete the oldest (first) entry.
    const oldest = map.keys().next().value;
    if (oldest !== undefined) map.delete(oldest);
  }
};

/**
 * Only adjust scroll when the item was entirely above the viewport before
 * the size change.  TanStack Virtual's default heuristic
 * (`item.start < scrollOffset`) fires for any item whose top is above the
 * fold — including the currently-viewed streaming message when it is tall.
 * That causes visible jitter because every growth delta shifts scrollTop,
 * moving the content the user is reading.
 *
 * The `item` TanStack hands this predicate is the *cached* measurement, so
 * `item.start + item.size` is the item's end *before* this resize — its
 * pre-growth end.  We compensate only when that pre-growth end was at or above
 * `scrollOffset`, i.e. the item was completely out of view above the viewport.
 * (`delta`, the size change, is intentionally not subtracted: the cached
 * `item.size` is already the pre-growth size, so `item.start + item.size` is the
 * pre-growth end as written.)
 */
export const shouldAdjustScrollPosition = (
  item: VirtualItem,
  delta: number,
  instance: Virtualizer<HTMLDivElement, Element>,
): boolean => {
  const scrollOffset = instance.scrollOffset ?? 0;
  const previousEnd = item.start + item.size;
  return previousEnd <= scrollOffset;
};

/**
 * Consume-once-by-index suppression for the virtualizer's per-item scroll
 * compensation. Used by callers that intentionally resize a known message
 * (e.g. AlphaTable's wrap toggle) and want the viewport's "click point" to
 * stay anchored, even when the virtualizer would otherwise scroll to keep
 * the visible content stable.
 *
 * Set the index of the message about to resize via `skipNextScrollAdjustForItem`.
 * The next call to the wrapped `shouldAdjustScrollPositionOnItemSizeChange`
 * for that exact item index returns `false` once and clears the flag.
 */
let skipAdjustForItemIndex: number | null = null;

export const skipNextScrollAdjustForItem = (index: number): void => {
  skipAdjustForItemIndex = index;
};

/**
 * When this callback returns true, TanStack Virtual synchronously mutates
 * scrollTop and fires a `scroll` event indistinguishable from user input.
 * Flag `isProgrammaticScrollRef.current = true` first so chat-level scroll
 * listeners skip it.
 */
export const buildShouldAdjustScrollPositionOnItemSizeChange = (
  isMeasuring: () => boolean,
  isProgrammaticScrollRef?: MutableRefObject<boolean>,
): ((item: VirtualItem, delta: number, instance: Virtualizer<HTMLDivElement, Element>) => boolean) => {
  return (item, delta, instance): boolean => {
    if (isMeasuring()) return false;
    if (skipAdjustForItemIndex !== null && item.index === skipAdjustForItemIndex) {
      skipAdjustForItemIndex = null;
      return false;
    }
    const shouldAdjust = shouldAdjustScrollPosition(item, delta, instance);
    if (shouldAdjust && isProgrammaticScrollRef) isProgrammaticScrollRef.current = true;
    return shouldAdjust;
  };
};

export const useAlphaVirtualizer = (
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  messageCount: number,
  lastMessageRole: ChatMessageRole | null,
  agentId: string,
  machine: ScrollStateMachine,
  introPaddingStart: number = VIRTUAL_PADDING,
  // Set true when an item size change triggers a scrollTop adjustment,
  // so chat-level scroll listeners can distinguish it from a user scroll.
  isProgrammaticScrollRef?: MutableRefObject<boolean>,
  // Whether the agent is streaming — drives the paddingEnd floor (see
  // dynamicPaddingEnd below).
  isStreaming: boolean = false,
): Virtualizer<HTMLDivElement, Element> => {
  const [containerHeight, setContainerHeight] = useState(0);
  const [tailContentHeight, setTailContentHeight] = useState(0);
  const tailContentHeightRef = useRef(0);
  const prevAgentIdRef = useRef(agentId);

  // Per-agent caches: item heights (for estimateSize) and tail content height.
  // When switching away from an agent we save these; when switching back we
  // restore them so items start at approximately-correct positions instead of
  // the generic 120px estimate and 64px padding fallback.
  const heightCacheRef = useRef<Map<string, Array<number>>>(new Map());
  const tailCacheRef = useRef<Map<string, number>>(new Map());
  const currentEstimatesRef = useRef<Array<number>>([]);

  // The settle window (per-item scroll-adjustment suppression after an agent
  // switch) is owned by the scroll state machine's layout phase: `measuring`
  // while heights/paddingEnd reconverge, `stable` once they have. Without that
  // suppression, items partially visible at the viewport top whose real heights
  // differ slightly from their saved estimates cause a small visible shift.
  const settlingRafRef = useRef(0);

  // Counter incremented after settling clears to force a re-render.
  // This guarantees the normal (non-agent-switch) branch of the layout
  // effect runs, which saves heights and recalculates tailContentHeight.
  // eslint-disable-next-line react/hook-use-state -- value unused; only the setter triggers re-renders
  const [, setSettleGeneration] = useState(0);
  const bumpSettleGeneration = useCallback(() => setSettleGeneration((c) => c + 1), []);

  // Track scroll container height via ResizeObserver so paddingEnd updates
  // on window resize.  The scroll container element is stable (no key={}
  // remount) so this effect only needs to run once.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    setContainerHeight(el.clientHeight);
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height;
      if (height != null) setContainerHeight(height);
    });
    observer.observe(el);
    return (): void => observer.disconnect();
  }, [scrollContainerRef]);

  // Cancel any pending settle-suppression frame on unmount. The agent-switch
  // branch schedules a requestAnimationFrame chain that ends in
  // bumpSettleGeneration() (a setState); without this cleanup it can fire
  // after the component is gone. Kept separate from the per-render layout
  // effect so it cancels only on unmount, not on every re-render.
  useEffect(() => {
    return (): void => cancelAnimationFrame(settlingRafRef.current);
  }, []);

  // The paddingEnd floor is streaming-scoped. While a stream is active — and
  // through the settle window after it ends, while late content changes (the
  // cursor unmounting, the turn footer mounting) can still land — the floor is
  // STREAMING_TAIL_PADDING: the pin keeps PIN_BOTTOM_GAP of it visible below
  // the content and relies on the remainder as slack below scrollTop, so the
  // turn-end shrink never clamps the scroll position. At rest the floor is
  // IDLE_TAIL_PADDING (== the pin gap), so the scroll range ends exactly at
  // the pin position: scrolling below the content reveals the gap and no more.
  // The drop happens with scrollTop at the post-drop range end, so it never
  // moves the view.
  const [isTailSettling, setIsTailSettling] = useState(false);
  useEffect(() => {
    if (isStreaming) {
      setIsTailSettling(true);
      return;
    }
    if (!isTailSettling) return;
    const timer = setTimeout(() => setIsTailSettling(false), FOOTER_REVEAL_WINDOW_MS);
    return (): void => clearTimeout(timer);
  }, [isStreaming, isTailSettling]);
  const tailPaddingFloor = isStreaming || isTailSettling ? STREAMING_TAIL_PADDING : IDLE_TAIL_PADDING;

  // paddingEnd needs to be just large enough for the scroll-to-top target
  // (the last user message) to reach the viewport top.  The required padding
  // = containerHeight - tailContentHeight, where tailContentHeight is the sum
  // of measured heights from the target user message to the end.  As the
  // assistant response grows, tailContentHeight increases and paddingEnd
  // shrinks — naturally constraining scroll range so content can't be pushed
  // off-screen.
  // Only apply dynamic padding once we have both container dimensions AND
  // real item measurements.  Before measurements land (tailContentHeight === 0),
  // using containerHeight alone would create a huge temporary paddingEnd that
  // destabilises scroll positions during view switches and agent restoration.
  const dynamicPaddingEnd =
    containerHeight > 0 && tailContentHeight > 0
      ? Math.max(containerHeight - tailContentHeight, tailPaddingFloor)
      : tailPaddingFloor;

  const virtualizer = useVirtualizer({
    count: messageCount,
    getScrollElement: () => scrollContainerRef.current,
    // Read from the per-agent height cache for unmeasured items.  After
    // measure() invalidates the measurement cache on agent switch, TanStack
    // Virtual calls estimateSize for each item — returning saved heights
    // from a previous visit gives approximately-correct positions instead
    // of the generic 120px fallback.
    //
    // Intentionally NOT memoised: TanStack Virtual's option reconciliation
    // uses reference equality, and a new reference each render triggers
    // internal recalculations that keep getTotalSize() in sync with
    // paddingEnd changes.
    estimateSize: (index: number): number => currentEstimatesRef.current[index] ?? ESTIMATED_MESSAGE_HEIGHT,
    overscan: OVERSCAN,
    paddingStart: introPaddingStart > 0 ? introPaddingStart : VIRTUAL_PADDING,
    paddingEnd: dynamicPaddingEnd,
  });

  // Sync tailContentHeight from virtualizer measurements after each render.
  // Intentionally has NO dependency array — this is a two-phase measurement
  // sync that can't use deps: paddingEnd depends on tailContentHeight, and
  // tailContentHeight depends on virtualizer measurements that are only
  // available after items render with the current paddingEnd.  Running after
  // every render resolves this circular dependency.  The cost is minimal
  // (at most 2 cache reads) and self-stabilises: setTailContentHeight only
  // fires when the sum actually changes, preventing cascading re-renders.
  //
  // Height cache note: heights are saved in the NORMAL branch (not the
  // agent-switch branch) because by the time the layout effect runs during
  // an agent switch, measureElement ref callbacks have already fired for the
  // INCOMING agent's items, contaminating measurementsCache.  Saving during
  // normal renders guarantees the cache holds the correct agent's heights.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    if (prevAgentIdRef.current !== agentId) {
      // Don't save outgoing agent's heights here — measurementsCache is
      // contaminated by the incoming agent's ref callbacks.  The outgoing
      // agent's correct heights were already saved during its last normal
      // (non-agent-switch) render.

      // The outgoing agent's settle hold is meaningless for the incoming agent;
      // its own isStreaming re-arms the hold if it is mid-stream.
      setIsTailSettling(false);

      // Restore saved state for the incoming agent.
      currentEstimatesRef.current = heightCacheRef.current.get(agentId) ?? [];
      const savedTail = tailCacheRef.current.get(agentId);

      if (savedTail != null) {
        // Return visit: use the exact tail height from last time.
        tailContentHeightRef.current = savedTail;
        setTailContentHeight(savedTail);
      } else if (messageCount > 0) {
        // First visit: seed tailContentHeight from height estimates so
        // paddingEnd is approximately correct on the first render instead
        // of falling back to the 64px VIRTUAL_PADDING default.
        const targetIndex = lastMessageRole === ChatMessageRole.USER ? messageCount - 1 : Math.max(messageCount - 2, 0);
        let sum = 0;
        for (let i = targetIndex; i < messageCount; i++) {
          sum += currentEstimatesRef.current[i] ?? ESTIMATED_MESSAGE_HEIGHT;
        }

        if (sum > 0) {
          tailContentHeightRef.current = sum;
          setTailContentHeight(sum);
        }
      }

      prevAgentIdRef.current = agentId;

      // Always invalidate the measurement cache — it holds the outgoing
      // agent's heights which are stale for the incoming agent.  estimateSize
      // returns saved heights from the per-agent cache, so the recalculated
      // positions are close to correct.
      virtualizer.measure();

      // Enter the `measuring` layout phase to suppress per-item scroll
      // adjustments until measurements settle.
      machine.dispatchLayout({ kind: "invalidated", agentId });
      cancelAnimationFrame(settlingRafRef.current);
      settlingRafRef.current = requestAnimationFrame(() => {
        settlingRafRef.current = requestAnimationFrame(() => {
          machine.dispatchLayout({ kind: "converged" });
          settlingRafRef.current = 0;
          // Force a re-render so the normal branch runs, which saves
          // heights and recalculates tailContentHeight.
          bumpSettleGeneration();
        });
      });

      // Skip tail recalculation — we've already set tailContentHeight
      // (from cache or estimates).
      return;
    }

    if (messageCount === 0) return;

    // While measurements are settling after a tab switch, hold paddingEnd
    // stable by skipping both the tail recalculation and height saving.
    // The cached tailContentHeight (restored above) stays in effect until
    // settling completes, preventing a visible shift from intermediate
    // measurement values.
    if (machine.getState().layout.kind === "measuring") return;

    // The scroll-to-top target is the last user message: the last item when
    // it's from the user, otherwise the second-to-last item.
    const targetIndex = lastMessageRole === ChatMessageRole.USER ? messageCount - 1 : Math.max(messageCount - 2, 0);

    let sum = 0;
    for (let i = targetIndex; i < messageCount; i++) {
      sum += virtualizer.measurementsCache[i]?.size ?? 0;
    }

    if (sum !== tailContentHeightRef.current) {
      tailContentHeightRef.current = sum;
      setTailContentHeight(sum);
    }

    // Save current agent's heights after every stable render.  This
    // ensures the cache always has correct measurements from the last
    // render where the agent's own items were measured — never heights
    // contaminated by another agent's ref callbacks.
    const heights: Array<number> = [];
    for (let i = 0; i < virtualizer.measurementsCache.length; i++) {
      const item = virtualizer.measurementsCache[i];
      if (item) heights[i] = item.size;
    }
    heightCacheRef.current.set(agentId, heights);
    tailCacheRef.current.set(agentId, tailContentHeightRef.current);
    touchLRU(heightCacheRef.current, agentId, MAX_CACHED_AGENTS);
    touchLRU(tailCacheRef.current, agentId, MAX_CACHED_AGENTS);
  });

  virtualizer.shouldAdjustScrollPositionOnItemSizeChange = buildShouldAdjustScrollPositionOnItemSizeChange(
    () => machine.getState().layout.kind === "measuring",
    isProgrammaticScrollRef,
  );

  return virtualizer;
};
