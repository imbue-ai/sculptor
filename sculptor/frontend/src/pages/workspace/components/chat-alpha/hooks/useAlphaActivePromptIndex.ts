import type { Virtualizer } from "@tanstack/react-virtual";
import { throttle } from "lodash";
import type { MutableRefObject, RefObject } from "react";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import type { ScrollStateMachine } from "../scroll/scrollStateMachine.ts";

/**
 * How far below the current scrollTop a prompt's virtual start position can be
 * and still be considered "scrolled to". Needs to exceed the virtualizer's
 * paddingStart (~64px) so the first prompt registers as active on mount.
 */
const SCROLL_THRESHOLD_PX = 200;

const SCROLL_THROTTLE_MS = 100;

/**
 * After a programmatic cursor update (via `setIndex`), we skip scroll-spy
 * updates for this long so the async scroll events from `scrollToIndex`
 * can't clobber the just-set cursor.  The window is released immediately
 * when the user scrolls manually (wheel/touch) so the dot rail resumes
 * tracking their intent.
 */
const PROGRAMMATIC_SCROLL_WINDOW_MS = 500;

export type ActivePromptIndex = {
  /** Effective active prompt index (scroll-derived, or last when pinned to bottom). */
  index: number;
  /** Ref mirroring `index` for synchronous reads from event handlers. */
  ref: MutableRefObject<number>;
  /** Force the active index (e.g. keyboard nav). Subsequent scrolls may overwrite. */
  setIndex: (idx: number) => void;
  /**
   * True when the user has scrolled past the top of the active prompt — i.e.
   * the prompt's virtual top edge is above the current scrollTop (with a small
   * tolerance).  Lets keyboard nav scroll the active turn back to the top
   * first before moving to the previous turn.
   */
  isScrolledPastActive: () => boolean;
};

/**
 * Tolerance for `isScrolledPastActive`.  `scrollToIndex({ align: "start" })`
 * should land scrollTop ≈ prompt.start, so a small epsilon absorbs sub-pixel
 * rounding without triggering the "scroll to top of turn" branch when the
 * user is effectively already at the top.
 */
const SCROLL_PAST_ACTIVE_TOLERANCE_PX = 20;

/**
 * Tracks the index (into `userPromptIndices`) of the user prompt currently
 * nearest the top of the viewport.  Returns the last index when the user is
 * pinned at the bottom of the conversation.
 *
 * Uses `virtualizer.measurementsCache` to look up virtual Y positions without
 * requiring DOM elements to be present — necessary because alpha chat
 * virtualizes off-screen messages out of the DOM.
 */
export const useAlphaActivePromptIndex = (
  userPromptIndices: ReadonlyArray<number>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  isAtBottom: boolean,
  machine: ScrollStateMachine,
): ActivePromptIndex => {
  const [activeIndex, setActiveIndex] = useState<number>(0);

  // Whether keyboard prompt navigation is active, read off the scroll state
  // machine's `navigating` phase. Suppresses the stick-to-bottom highlight so
  // the explicit nav cursor isn't clobbered.
  const isNavigating = useSyncExternalStore(
    machine.subscribe,
    () => machine.getState().authority.kind === "navigating",
  );

  // Timestamp (ms, Date.now) until which the scroll-spy should skip updates
  // so programmatic scrolls from `setIndex` / `scrollToIndex` can't clobber
  // the just-set cursor.  Reset to 0 on any user-initiated scroll input.
  const programmaticScrollUntilRef = useRef<number>(0);

  // Keep a ref so the throttled handler always reads the latest value without
  // being recreated on every render.  Written in an effect (not during render)
  // because the ref is only consumed in scroll/callbacks, never read in render.
  const userPromptIndicesRef = useRef(userPromptIndices);
  useEffect(() => {
    userPromptIndicesRef.current = userPromptIndices;
  });

  // Track whether we were at the bottom on the previous committed render.  When
  // a new message is added the content height jumps before auto-scroll catches
  // up, so `isAtBottom` can briefly flicker to false.  By remembering that we
  // WERE at the bottom we can hold the last-dot highlight through that gap.
  // The refs are written in an effect (after commit) so they hold the previous
  // render's values across exactly one external re-render; the read below feeds
  // `shouldStickToBottom`, which can only be computed from the prior render and
  // therefore cannot be lifted to state without collapsing that one-render hold.
  const wasAtBottomRef = useRef(isAtBottom);
  const prevLengthRef = useRef(userPromptIndices.length);

  // Prev-render tracker: reads the previous committed render's values (written
  // by the effect below). This can only be derived from the prior render, so it
  // cannot be lifted to state without collapsing the one-render hold.
  const shouldStickToBottom =
    isAtBottom ||
    // eslint-disable-next-line react-hooks/refs
    (wasAtBottomRef.current && userPromptIndices.length >= prevLengthRef.current);

  useEffect(() => {
    wasAtBottomRef.current = isAtBottom;
    prevLengthRef.current = userPromptIndices.length;
  });

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const compute = (): void => {
      // During the programmatic-scroll window (just after setIndex), ignore
      // scroll events so the async scroll from `scrollToIndex` doesn't
      // clobber the cursor.  The window is cancelled on user input below.
      if (Date.now() < programmaticScrollUntilRef.current) return;

      const scrollTop = el.scrollTop;
      const indices = userPromptIndicesRef.current;

      if (indices.length === 0) {
        setActiveIndex(0);
        return;
      }

      // The active prompt is the last one whose virtual top edge has been
      // scrolled to (i.e. start ≤ scrollTop + threshold). Prompts are in
      // document order so we can stop as soon as one exceeds the threshold.
      let active = 0;
      for (let i = 0; i < indices.length; i++) {
        const msgIdx = indices[i];
        const start = virtualizer.measurementsCache[msgIdx]?.start ?? 0;
        if (start <= scrollTop + SCROLL_THRESHOLD_PX) {
          active = i;
        } else {
          break;
        }
      }

      setActiveIndex(active);
    };

    const throttledCompute = throttle(compute, SCROLL_THROTTLE_MS, { leading: true, trailing: true });

    // User-initiated scroll input cancels the programmatic-scroll freeze so
    // the dot rail resumes tracking real scroll position immediately, even
    // if the window hasn't expired yet (e.g. user starts wheeling right
    // after a dot click).
    const onUserScrollInput = (): void => {
      programmaticScrollUntilRef.current = 0;
    };

    // Compute immediately so the active dot is correct on first render.
    compute();
    el.addEventListener("scroll", throttledCompute, { passive: true });
    el.addEventListener("wheel", onUserScrollInput, { passive: true });
    el.addEventListener("touchstart", onUserScrollInput, { passive: true });
    el.addEventListener("touchmove", onUserScrollInput, { passive: true });
    return (): void => {
      throttledCompute.cancel();
      el.removeEventListener("scroll", throttledCompute);
      el.removeEventListener("wheel", onUserScrollInput);
      el.removeEventListener("touchstart", onUserScrollInput);
      el.removeEventListener("touchmove", onUserScrollInput);
    };
  }, [scrollContainerRef, virtualizer]);

  // When pinned to the bottom (or holding through the brief isAtBottom gap
  // after a new message is added), highlight the last prompt dot.  Suppressed
  // during keyboard navigation so the explicit cursor isn't clobbered.
  const effectiveIndex =
    !isNavigating && shouldStickToBottom && userPromptIndices.length > 0 ? userPromptIndices.length - 1 : activeIndex;

  // Mirror the effective index into a ref so arrow-key handlers can read it
  // synchronously without waiting for a re-render.  `setIndex` writes it
  // eagerly; this effect keeps it in sync after scroll-spy driven updates.
  const indexRef = useRef(effectiveIndex);
  useEffect(() => {
    indexRef.current = effectiveIndex;
  });

  const setIndex = useCallback((idx: number): void => {
    indexRef.current = idx;
    // Open a short window where scroll-spy updates are ignored so the async
    // scroll events from the scrollToIndex call that typically follows
    // setIndex can't clobber this cursor.
    programmaticScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_WINDOW_MS;
    setActiveIndex(idx);
  }, []);

  const isScrolledPastActive = useCallback((): boolean => {
    const el = scrollContainerRef.current;
    if (!el) return false;
    const indices = userPromptIndicesRef.current;
    const activeIdx = indexRef.current;
    if (activeIdx < 0 || activeIdx >= indices.length) return false;
    const msgIdx = indices[activeIdx];
    const start = virtualizer.measurementsCache[msgIdx]?.start;
    if (start == null) return false;
    return el.scrollTop > start + SCROLL_PAST_ACTIVE_TOLERANCE_PX;
  }, [scrollContainerRef, virtualizer]);

  return { index: effectiveIndex, ref: indexRef, setIndex, isScrolledPastActive };
};
