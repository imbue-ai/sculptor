import type { Virtualizer } from "@tanstack/react-virtual";
import type { MutableRefObject, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ChatMessageRole } from "~/api";

const BOTTOM_THRESHOLD = 200;
// Tighter threshold for re-engaging auto-scroll. The user must scroll to
// essentially the very bottom — not just "near" it — to opt back in.
const REENGAGE_THRESHOLD = 5;
// How many px before the viewport edge to transition from filling phase to
// pin-to-bottom.  The ResizeObserver fires after content grows, so without
// this buffer the content briefly overshoots the viewport before locking.
const FILLING_OVERFLOW_BUFFER = 100;

// Fixed duration for the scroll-to-top animation (ms). Same speed
// regardless of distance so short and long scrolls feel consistent.
const SCROLL_ANIMATION_MS = 250;
const SCROLL_ANIMATION_EASING = "cubic-bezier(0.33, 1, 0.68, 1)"; // ease-out

/** Cancel any in-progress scroll-to-top transform animation and restore
 *  the virtualizer's scroll-position adjustment callback. */
const clearScrollAnimation = (
  el: HTMLElement | null,
  timerRef: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
  virtualizer?: Virtualizer<HTMLDivElement, Element>,
  savedAdjustRef?: React.MutableRefObject<
    Virtualizer<HTMLDivElement, Element>["shouldAdjustScrollPositionOnItemSizeChange"] | null
  >,
): void => {
  if (timerRef.current !== null) {
    clearTimeout(timerRef.current);
    timerRef.current = null;
  }
  const content = el?.firstElementChild as HTMLElement | null;
  if (content) {
    content.style.transition = "";
    content.style.transform = "";
  }

  if (virtualizer && savedAdjustRef?.current != null) {
    virtualizer.shouldAdjustScrollPositionOnItemSizeChange = savedAdjustRef.current;
    savedAdjustRef.current = null;
  }
};

type UseAlphaAutoScrollReturn = {
  isEngaged: boolean;
  isAtBottom: boolean;
  scrollToBottom: () => void;
  scrollToTop: () => void;
  isSuppressed: boolean;
  setIsSuppressed: (val: boolean) => void;
  isProgrammaticScrollRef: React.MutableRefObject<boolean>;
  // True for ~150ms after a wheel/touch/keydown on the chat container.
  // Exposed so ChatScrollProvider can share the same user-input signal
  // instead of duplicating the listener plumbing.
  isUserScrollingRef: React.MutableRefObject<boolean>;
  isJumpSuppressed: boolean;
};

export const useAlphaAutoScroll = (
  scrollContainerRef: RefObject<HTMLDivElement | null>,
  isStreaming: boolean,
  messageCount: number,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  lastMessageRole: ChatMessageRole | null,
  lastUserMessageIndex: number,
  taskId: string,
  // Pass a shared ref to flag programmatic scrolls from outside this hook
  // (e.g. the virtualizer's item-size adjustments). Falls back to an
  // internal ref when omitted.
  externalProgrammaticScrollRef?: MutableRefObject<boolean>,
): UseAlphaAutoScrollReturn => {
  const [isEngaged, setIsEngaged] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [isSuppressed, setIsSuppressed] = useState(false);
  const internalProgrammaticScroll = useRef(false);
  const isProgrammaticScroll = externalProgrammaticScrollRef ?? internalProgrammaticScroll;

  // Filling phase: user message is anchored at the top, response grows below.
  // Ref-only (not state) because this value is never rendered — it's only read
  // by ResizeObserver callbacks and scroll handlers.  Using state would cause
  // unnecessary re-renders and ResizeObserver teardown/recreation on each
  // transition.
  const isFillingRef = useRef(false);
  // The virtualizer index to anchor at the top during filling.  The
  // ResizeObserver re-applies this on each resize because virtualizer
  // size corrections can clamp scrollTop below the intended target.
  const fillingAnchorIndexRef = useRef(-1);

  // Suppress the jump-to-bottom button between message send and response arrival.
  const [isJumpSuppressed, setIsJumpSuppressed] = useState(false);

  // Track previous message count and last user message index to detect new user messages.
  const prevMessageCountRef = useRef(messageCount);
  const prevLastUserMessageIndexRef = useRef(lastUserMessageIndex);

  // Track scroll direction so REENGAGE_THRESHOLD only fires when the user
  // deliberately scrolls back to the bottom (not when they scroll up and
  // land within 5px).  -1 = uninitialized (no direction info yet).
  const prevScrollTopRef = useRef(-1);

  // Synchronous ref mirror of isAtBottom, updated in the scroll handler before
  // React batches the state update.  The pin-to-bottom layout effect reads this
  // ref so it never acts on stale state (e.g. the user just scrolled away but
  // React hasn't re-rendered yet).
  const isAtBottomRef = useRef(true);

  // Synchronous ref mirrors of isEngaged, isStreaming, and isSuppressed, read
  // by the scroll handler and effects so they can make decisions without stale closures.
  const isEngagedRef = useRef(false);
  const isStreamingRef = useRef(isStreaming);
  isStreamingRef.current = isStreaming;
  const isSuppressedRef = useRef(isSuppressed);
  isSuppressedRef.current = isSuppressed;

  // Track whether the user is actively scrolling via input devices (wheel,
  // touch, keyboard).  Only user-initiated scrolls can engage or disengage
  // auto-scroll.  Programmatic scrolls (TanStack Virtual's internal
  // measurement-correction loop, scrollToIndex, etc.) fire `scroll` events
  // but never `wheel`/`touch`/`keydown`, so they are ignored.
  const isUserScrollingRef = useRef(false);
  const userScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const USER_SCROLL_DEBOUNCE_MS = 150;

  // Timer handle for clearing the transform animation styles.
  const scrollAnimationRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Saved shouldAdjustScrollPositionOnItemSizeChange, suppressed during animation.
  const savedScrollAdjustRef = useRef<
    Virtualizer<HTMLDivElement, Element>["shouldAdjustScrollPositionOnItemSizeChange"] | null
  >(null);

  // Mark that the user is actively scrolling, with a debounce to clear it.
  const markUserScrolling = useCallback((): void => {
    isUserScrollingRef.current = true;
    if (userScrollTimerRef.current !== null) {
      clearTimeout(userScrollTimerRef.current);
    }
    userScrollTimerRef.current = setTimeout(() => {
      isUserScrollingRef.current = false;
      userScrollTimerRef.current = null;
    }, USER_SCROLL_DEBOUNCE_MS);
  }, []);

  // Listen for user input events that indicate intentional scrolling.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const onUserInput = (): void => {
      markUserScrolling();
      // Disengage immediately on any user wheel/touch input — before any scroll
      // event fires.  The ResizeObserver fires on every content growth during
      // streaming, sets isProgrammaticScroll, and calls scrollToIndex.  If the
      // user's resulting scroll event then sees isProgrammaticScroll=true it gets
      // consumed as "programmatic" and scroll-lock is never released.  Disengaging
      // here short-circuits that race: once isEngagedRef is false the ResizeObserver
      // returns early and stops scrolling, so there is nothing left to consume the
      // user's scroll event.  Skip during filling phase — that cleanup requires
      // clearing the CSS animation and is handled correctly in the scroll handler.
      if (!isSuppressedRef.current && isEngagedRef.current && !isFillingRef.current) {
        isEngagedRef.current = false;
        setIsEngaged(false);
        // Reset direction tracking: the next scroll event could land anywhere
        // relative to the current position, and we don't want a stale
        // prevScrollTop to cause a false "scrolling down" classification.
        prevScrollTopRef.current = -1;
      }
    };
    el.addEventListener("wheel", onUserInput, { passive: true });
    el.addEventListener("touchstart", onUserInput, { passive: true });
    el.addEventListener("touchmove", onUserInput, { passive: true });
    el.addEventListener("keydown", onUserInput, { passive: true });

    return (): void => {
      el.removeEventListener("wheel", onUserInput);
      el.removeEventListener("touchstart", onUserInput);
      el.removeEventListener("touchmove", onUserInput);
      el.removeEventListener("keydown", onUserInput);
      if (userScrollTimerRef.current !== null) {
        clearTimeout(userScrollTimerRef.current);
      }
    };
  }, [scrollContainerRef, markUserScrolling]);

  // Scroll event listener — only processes engage/disengage when the scroll
  // was initiated by the user (isUserScrollingRef is true).
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;

    const handleScroll = (): void => {
      const currentScrollTop = el.scrollTop;
      // Compute direction before any early return so prevScrollTopRef is
      // always up-to-date.  Programmatic scrolls (e.g. ResizeObserver
      // scrolling to bottom) also update it, which means the next user scroll
      // correctly measures direction relative to where the programmatic scroll
      // landed — preventing false "scrolling down" detection when the user
      // actually scrolled up from the bottom.
      const prevScrollTop = prevScrollTopRef.current;
      prevScrollTopRef.current = currentScrollTop;
      const isScrollingDown = prevScrollTop !== -1 && currentScrollTop >= prevScrollTop;

      const distance = el.scrollHeight - currentScrollTop - el.clientHeight;
      const isNearBottom = distance <= BOTTOM_THRESHOLD;
      // During filling phase, don't mark as "at bottom" — virtualizer size
      // corrections can temporarily shrink scrollHeight so the scroll-to-top
      // position appears near the bottom.  Allowing isAtBottomRef to flip
      // true would let pin-to-bottom fire on the next render, undoing the
      // scroll-to-top.
      if (!isFillingRef.current || !isNearBottom) {
        isAtBottomRef.current = isNearBottom;
        setIsAtBottom(isNearBottom);
      }

      if (isProgrammaticScroll.current) {
        isProgrammaticScroll.current = false;
        return;
      }

      if (isSuppressed) return;

      // Ignore non-user scrolls (TanStack corrections, ResizeObserver, etc.)
      if (!isUserScrollingRef.current) return;

      // User scroll during filling phase exits the anchor and cancels
      // any in-progress scroll animation.
      if (isFillingRef.current) {
        isFillingRef.current = false;
        fillingAnchorIndexRef.current = -1;
        setIsJumpSuppressed(false);
        clearScrollAnimation(scrollContainerRef.current, scrollAnimationRef, virtualizer, savedScrollAdjustRef);
      }

      if (isEngagedRef.current) {
        // Any user-initiated scroll while engaged disengages auto-scroll,
        // regardless of position. Even a tiny scroll near the bottom should
        // stop the view from being pulled back.
        isEngagedRef.current = false;
        setIsEngaged(false);
      } else if (isStreamingRef.current && isScrollingDown && distance <= REENGAGE_THRESHOLD) {
        // User scrolled back to the very bottom during streaming — re-engage.
        // Requires isScrollingDown so this never fires when the user is
        // scrolling UP: without the guard, a tiny upward scroll (< 5px) from
        // the absolute bottom would immediately re-engage after the wheel
        // handler disengaged, negating the user's intent.
        isEngagedRef.current = true;
        setIsEngaged(true);
      }
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return (): void => el.removeEventListener("scroll", handleScroll);
  }, [scrollContainerRef, isSuppressed, virtualizer, isProgrammaticScroll]);

  // Reset auto-scroll state on task switch.  Without this, stale state from
  // the previous agent leaks into the new agent's first render — e.g.
  // isAtBottom=true from agent A causes pin-to-bottom to fire for agent B,
  // and a higher lastUserMessageIndex triggers a spurious scroll-to-top
  // animation.  This effect MUST be declared before scroll-to-top and
  // pin-to-bottom so it runs first in the layout-effect queue.
  const prevAutoScrollTaskRef = useRef(taskId);
  useLayoutEffect(() => {
    if (prevAutoScrollTaskRef.current !== taskId) {
      prevAutoScrollTaskRef.current = taskId;
      prevMessageCountRef.current = messageCount;
      prevLastUserMessageIndexRef.current = lastUserMessageIndex;
      isAtBottomRef.current = false;
      isEngagedRef.current = false;
      isFillingRef.current = false;
      fillingAnchorIndexRef.current = -1;
      prevScrollTopRef.current = -1;
      clearScrollAnimation(scrollContainerRef.current, scrollAnimationRef, virtualizer, savedScrollAdjustRef);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // Scroll-to-top: when a new user message appears, animate it to the top of
  // the viewport, enter filling phase, and force-engage auto-scroll.
  //
  // Uses lastUserMessageIndex (not lastMessageRole) to detect new user
  // messages.  This handles the case where the user message and the first
  // assistant response arrive in the same React render batch — in that
  // scenario lastMessageRole would be ASSISTANT, causing scroll-to-top
  // to be skipped.
  useLayoutEffect(() => {
    const isNewUserMessage = lastUserMessageIndex > prevLastUserMessageIndexRef.current;
    prevMessageCountRef.current = messageCount;
    prevLastUserMessageIndexRef.current = lastUserMessageIndex;

    if (!isNewUserMessage || messageCount === 0 || isSuppressed) return;
    if (lastUserMessageIndex < 0) return;

    // For the first user message, skip the scroll-to-top animation so the
    // chat intro stays visible.  But still enter filling phase: without it,
    // the large virtualizer paddingEnd makes distance > BOTTOM_THRESHOLD,
    // so the streaming-start engagement check fails and auto-scroll never
    // kicks in.  The filling phase ResizeObserver detects overflow and
    // transitions to pin-to-bottom exactly as it does for later messages.
    if (lastUserMessageIndex === 0) {
      isAtBottomRef.current = false;
      setIsAtBottom(false);
      isFillingRef.current = true;
      fillingAnchorIndexRef.current = 0;
      isEngagedRef.current = true;
      setIsEngaged(true);
      setIsJumpSuppressed(true);
      return;
    }

    const el = scrollContainerRef.current;
    if (!el) return;

    // Cancel any in-progress animation from a previous send.
    clearScrollAnimation(el, scrollAnimationRef, virtualizer, savedScrollAdjustRef);

    // Record where we are before scrolling.
    const startScrollTop = el.scrollTop;

    // Suppress the virtualizer's scroll-position corrections during the
    // animation — they would shift scrollTop mid-transition and cause a
    // visible bounce.
    savedScrollAdjustRef.current = virtualizer.shouldAdjustScrollPositionOnItemSizeChange;
    virtualizer.shouldAdjustScrollPositionOnItemSizeChange = (): boolean => false;

    // Ensure the scroll container has enough room below the target for the
    // message to reach the viewport top.  The virtualizer's paddingEnd may
    // be based on a stale tailContentHeight from the previous render (the
    // state update hasn't taken effect yet).  Without this correction,
    // scrollToIndex gets clamped by both the virtualizer's internal
    // getTotalSize() and the browser's scrollHeight, and the user message
    // ends up mid-viewport instead of at the top.
    const targetItem = virtualizer.measurementsCache?.[lastUserMessageIndex];
    if (targetItem) {
      const neededPadding = el.clientHeight - targetItem.size;
      if (neededPadding > (virtualizer.options.paddingEnd ?? 0)) {
        virtualizer.options.paddingEnd = neededPadding;
        const contentEl = el.firstElementChild as HTMLElement | null;
        if (contentEl) {
          contentEl.style.height = `${virtualizer.getTotalSize()}px`;
        }
      }
    }

    virtualizer.scrollToIndex(lastUserMessageIndex, { align: "start" });

    // Synchronously mark that we're no longer at the bottom.  The scroll
    // event that would normally update isAtBottomRef fires asynchronously,
    // so without this the pin-to-bottom layout effect (which runs in the
    // same render) would still see the stale `true` and scroll to the end,
    // undoing the scroll-to-top.
    isAtBottomRef.current = false;
    setIsAtBottom(false);

    isProgrammaticScroll.current = true;

    isFillingRef.current = true;
    fillingAnchorIndexRef.current = lastUserMessageIndex;
    isEngagedRef.current = true;
    setIsEngaged(true);
    setIsJumpSuppressed(true);

    // Animate with a CSS transform on the content wrapper. The scroll
    // position is already correct (virtualizer is in sync), so we offset
    // the content visually and transition back to translateY(0).
    const delta = el.scrollTop - startScrollTop;
    const content = el.firstElementChild as HTMLElement | null;
    if (content && Math.abs(delta) > 1) {
      content.style.transition = "none";
      content.style.transform = `translateY(${delta}px)`;
      // Force style recalculation so the starting position applies.
      void content.offsetHeight;
      content.style.transition = `transform ${SCROLL_ANIMATION_MS}ms ${SCROLL_ANIMATION_EASING}`;
      content.style.transform = "translateY(0)";

      scrollAnimationRef.current = setTimeout(() => {
        content.style.transition = "";
        content.style.transform = "";
        virtualizer.shouldAdjustScrollPositionOnItemSizeChange = savedScrollAdjustRef.current!;
        savedScrollAdjustRef.current = null;
        scrollAnimationRef.current = null;
      }, SCROLL_ANIMATION_MS);
    } else {
      // No animation needed — restore corrections immediately.
      virtualizer.shouldAdjustScrollPositionOnItemSizeChange = savedScrollAdjustRef.current!;
      savedScrollAdjustRef.current = null;
    }
  }, [lastUserMessageIndex, messageCount, isSuppressed, virtualizer, scrollContainerRef, isProgrammaticScroll]);

  // Pin-to-bottom: when new non-user messages arrive while the user is at the
  // bottom, scroll to show the new content immediately (before streaming even
  // starts).  Skips when scroll-to-top handles the message (user messages) or
  // when in filling phase.
  // Uses isAtBottomRef (not state) to avoid a race where isAtBottom state is
  // stale (e.g. the user just scrolled away but React hasn't re-rendered yet).
  useLayoutEffect(() => {
    if (messageCount === 0 || !isAtBottom || isSuppressed) return;
    if (!isAtBottomRef.current) return;
    // During the filling phase (scroll-to-top anchor), skip pin-to-bottom
    // while streaming.  For non-streaming responses, clear the stuck filling
    // state so pin-to-bottom can proceed normally.
    if (isFillingRef.current) {
      if (isStreamingRef.current) return;
      isFillingRef.current = false;
      fillingAnchorIndexRef.current = -1;
    }
    if (lastMessageRole === ChatMessageRole.USER) return;
    virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
  }, [messageCount, isAtBottom, isSuppressed, virtualizer, lastMessageRole]);

  // Engage when streaming starts while at bottom; disengage when streaming stops.
  // Reads the live scroll position rather than the isAtBottom state, which can be
  // stale when a new user message grew the content between the last scroll event
  // and streaming starting.  Uses isSuppressedRef so the closure always sees the
  // latest value without needing isSuppressed in the dependency array.
  useEffect(() => {
    if (isStreaming && !isSuppressedRef.current) {
      // Don't re-engage via distance check if we're in filling phase —
      // the scroll-to-top effect already engaged.
      if (!isFillingRef.current) {
        const el = scrollContainerRef.current;
        if (el) {
          const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
          if (distance <= BOTTOM_THRESHOLD) {
            isEngagedRef.current = true;
            setIsEngaged(true);
          }
        }
      }
    } else if (!isStreaming) {
      // Final scroll-to-bottom before disengaging: the ResizeObserver
      // disconnects when streaming stops, so any subsequent virtualizer
      // re-measurements (item size corrections, paddingEnd changes) won't
      // be compensated.  A single scrollToIndex here anchors the view at
      // the bottom before those adjustments land.
      // Reads messageCount and virtualizer from the closure (current render
      // values) without adding them to deps — this branch only matters on
      // the isStreaming transition, not on every messageCount change.
      // Skip when still in filling phase (short response that never overflowed) —
      // the inflated paddingEnd causes scrollToIndex to land near scrollTop=0.
      // Also skip when already at the very bottom (liveDistance ≤ 1px): the
      // ResizeObserver kept us there during streaming, so re-firing here would
      // cause a visible jump if paddingEnd changed in this same render.
      if (isEngagedRef.current && messageCount > 0 && !isFillingRef.current) {
        const el = scrollContainerRef.current;
        const liveDistance = el ? el.scrollHeight - el.scrollTop - el.clientHeight : 0;
        if (liveDistance > 1) {
          isProgrammaticScroll.current = true;
          virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
        }
      }
      isEngagedRef.current = false;
      setIsEngaged(false);
      // Clear filling phase when streaming ends (short response — never overflowed).
      // If the response had overflowed, the ResizeObserver would have already
      // cleared filling phase before we get here.  If the user had scrolled away,
      // the scroll handler would have cleared it.  Reaching this block means the
      // response fit entirely in the viewport and the user stayed put — there is
      // nothing to scroll to, so set isAtBottom = true unconditionally.  A live
      // distance check is incorrect here: the large virtualizer paddingEnd inflates
      // scrollHeight so distance > BOTTOM_THRESHOLD even though all content is visible.
      if (isFillingRef.current) {
        isFillingRef.current = false;
        fillingAnchorIndexRef.current = -1;
        setIsJumpSuppressed(false);
        isAtBottomRef.current = true;
        setIsAtBottom(true);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming, scrollContainerRef]);

  // Clear jump suppression when streaming starts (response has arrived),
  // UNLESS the filling phase is active — during filling, isAtBottom is
  // intentionally false (to prevent pin-to-bottom from overriding
  // scroll-to-top), so clearing suppression would cause the jump button
  // to appear even though the user is watching the response stream in.
  // Suppression is cleared later when filling ends.
  const prevStreamingForSuppressRef = useRef(isStreaming);
  useEffect(() => {
    if (isStreaming && !prevStreamingForSuppressRef.current && !isFillingRef.current) {
      setIsJumpSuppressed(false);
    }
    prevStreamingForSuppressRef.current = isStreaming;
  }, [isStreaming]);

  // Streaming ResizeObserver: single observer handles both isAtBottom tracking
  // and auto-scroll.  A single observer avoids redundant DOM reads — both tasks
  // need the same `distance` calculation on every content resize.
  //
  // isAtBottom tracking: updates isAtBottom state so the "jump to bottom" button
  // appears as soon as the bottom goes out of sight (no scroll event needed).
  //
  // Auto-scroll: when engaged, scrolls to bottom on content growth.  Uses refs
  // (isEngagedRef, isFillingRef) instead of state in the dep array so the
  // observer is not torn down and recreated on every engage/disengage or
  // filling-phase transition.
  useLayoutEffect(() => {
    if (!isStreaming || isSuppressed) return;
    const el = scrollContainerRef.current;
    const content = el?.firstElementChild;
    if (!el || !content) return;

    const observer = new ResizeObserver(() => {
      // Only user messages trigger scroll-to-top style scrolls.  During the
      // filling phase we intentionally do NOT re-anchor on each resize —
      // that produced visible scroll jitter every time the assistant
      // streamed a token or a subagent finished.  Viewport stability for
      // items above the fold is handled by shouldAdjustScrollPositionOnItemSizeChange
      // in useAlphaVirtualizer, which is enough to keep the user message
      // pinned at the top without firing scroll events on every resize.

      // Track isAtBottom for all streaming states (engaged or not).
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const isNearBottom = distance <= BOTTOM_THRESHOLD;
      // During filling phase, don't mark as "at bottom" — virtualizer size
      // corrections can temporarily shrink scrollHeight so the scroll-to-top
      // position appears near the bottom.
      if (!isFillingRef.current || !isNearBottom) {
        isAtBottomRef.current = isNearBottom;
        setIsAtBottom(isNearBottom);
      }

      // Auto-scroll logic — only when engaged with messages.
      if (!isEngagedRef.current || messageCount === 0) return;

      if (isFillingRef.current) {
        // Only check for overflow when the response has started arriving
        // (items exist after the anchor).  The user message itself may be
        // taller than the viewport — that's not an overflow of the response.
        const anchorIdx = fillingAnchorIndexRef.current;
        if (anchorIdx < 0 || messageCount <= anchorIdx + 1) return;

        // Overflow = the content BELOW the anchor message (the response)
        // is taller than the viewport.  We compare the height from the
        // anchor's end to the content bottom against clientHeight.
        // This avoids false positives when the anchor message itself is
        // taller than the viewport.
        const anchorItem = virtualizer.measurementsCache[anchorIdx];
        const anchorSize = anchorItem?.size ?? 0;
        const anchorEnd = anchorItem ? anchorItem.start + anchorSize : 0;
        const contentBottom = virtualizer.getTotalSize() - (virtualizer.options.paddingEnd ?? 0);
        const tailHeight = contentBottom - anchorEnd;
        // Overflow = response fills the remaining viewport space below the user message.
        // Compare tailHeight to (clientHeight - anchorSize), not full clientHeight —
        // the user message already occupies the top portion of the viewport.
        if (tailHeight >= el.clientHeight - anchorSize - FILLING_OVERFLOW_BUFFER) {
          // Response has overflowed — transition to pin-to-bottom.
          isFillingRef.current = false;
          fillingAnchorIndexRef.current = -1;
          setIsJumpSuppressed(false);
          isProgrammaticScroll.current = true;
          virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
        }
        // Otherwise response fits below the anchor — don't scroll, stay anchored.
        return;
      }

      // Only disengage if the user is actively scrolling away. Content growth
      // during streaming can temporarily push distance above the threshold even
      // though no user scroll happened (e.g. right after scrollToBottom()
      // re-engaged auto-scroll). The scroll event handler already disengages
      // on any user-initiated scroll, so this guard prevents false positives
      // from content-growth-induced distance spikes.
      if (distance > BOTTOM_THRESHOLD && isUserScrollingRef.current) {
        isEngagedRef.current = false;
        setIsEngaged(false);
        return;
      }
      isProgrammaticScroll.current = true;
      virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
    });

    // Initial scroll when engaging — skip during filling (scroll-to-top
    // already positioned the viewport).
    if (isEngagedRef.current && !isFillingRef.current && messageCount > 0) {
      const liveDistance = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (liveDistance <= BOTTOM_THRESHOLD) {
        isProgrammaticScroll.current = true;
        virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
      }
    }

    observer.observe(content);
    return (): void => observer.disconnect();
  }, [isStreaming, isSuppressed, messageCount, virtualizer, scrollContainerRef, isProgrammaticScroll]);

  const scrollToBottom = useCallback((): void => {
    if (messageCount === 0) return;
    isProgrammaticScroll.current = true;
    virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
    if (isStreaming) {
      isEngagedRef.current = true;
      setIsEngaged(true);
    }

    // Clear filling phase when user explicitly scrolls to bottom.
    if (isFillingRef.current) {
      isFillingRef.current = false;
      fillingAnchorIndexRef.current = -1;
      setIsJumpSuppressed(false);
    }
  }, [messageCount, virtualizer, isStreaming, isProgrammaticScroll]);

  const scrollToTop = useCallback((): void => {
    if (messageCount === 0) return;
    isProgrammaticScroll.current = true;
    virtualizer.scrollToIndex(0, { align: "start" });
    isEngagedRef.current = false;
    setIsEngaged(false);
    if (isFillingRef.current) {
      isFillingRef.current = false;
      fillingAnchorIndexRef.current = -1;
      setIsJumpSuppressed(false);
    }
  }, [messageCount, virtualizer, isProgrammaticScroll]);

  return {
    isEngaged,
    isAtBottom,
    scrollToBottom,
    scrollToTop,
    isSuppressed,
    setIsSuppressed,
    isProgrammaticScrollRef: isProgrammaticScroll,
    isUserScrollingRef,
    isJumpSuppressed,
  };
};
