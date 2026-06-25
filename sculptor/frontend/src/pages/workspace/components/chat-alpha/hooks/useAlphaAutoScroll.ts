/* eslint-disable react-hooks/immutability -- This hook imperatively controls
   scrolling: it deliberately mutates the TanStack virtualizer's internals
   (shouldAdjustScrollPositionOnItemSizeChange, options.paddingEnd) and shared
   programmatic-scroll refs to coordinate pin-to-bottom behavior. These
   mutations are intentional and cannot be expressed within the compiler's
   immutability model. */
import type { Virtualizer } from "@tanstack/react-virtual";
import type { MutableRefObject, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";

import { ChatMessageRole } from "~/api";

import { distanceFromContentBottom } from "../scroll/geometry.ts";
import { createScrollStateMachine, projectAtBottom, type ScrollStateMachine } from "../scroll/scrollStateMachine.ts";

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

// How long after a wheel/touch/keydown the user is still considered to be
// actively scrolling, before the user-scroll flag is debounced back off.
const USER_SCROLL_DEBOUNCE_MS = 150;

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
  // Read-only projection derived from the scroll state machine: true while
  // pinning to the bottom (following) or anchoring a new turn (filling).
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
  // The scroll state machine owns the auto-scroll authority: `following`
  // (pin-to-bottom) and `anchoringTurn` (the filling phase — a new user message
  // anchored at the top while its response grows below). This hook reads those
  // phases instead of keeping its own engaged/filling booleans, and dispatches
  // the events that drive them. Falls back to an internal machine when omitted
  // (e.g. in unit tests); the chat passes the shared one.
  externalMachine?: ScrollStateMachine,
  // Pass a shared ref to flag programmatic scrolls from outside this hook
  // (e.g. the virtualizer's item-size adjustments). Falls back to an
  // internal ref when omitted.
  externalProgrammaticScrollRef?: MutableRefObject<boolean>,
): UseAlphaAutoScrollReturn => {
  const [isSuppressed, setIsSuppressed] = useState(false);
  const internalProgrammaticScroll = useRef(false);
  const isProgrammaticScroll = externalProgrammaticScrollRef ?? internalProgrammaticScroll;
  // eslint-disable-next-line react/hook-use-state -- stable fallback instance; the setter is intentionally unused
  const [internalMachine] = useState(createScrollStateMachine);
  const machine = externalMachine ?? internalMachine;

  // Read the auto-scroll authority off the machine. `following` ⇒ pinning to the
  // bottom; `anchoringTurn` ⇒ filling phase, with `anchorIndex` naming the
  // virtualizer item anchored at the top. Wrapped in useCallback so they are
  // stable dependencies for the effects below (machine itself is stable).
  const isFollowing = useCallback((): boolean => machine.getState().authority.kind === "following", [machine]);
  const isAnchoring = useCallback((): boolean => machine.getState().authority.kind === "anchoringTurn", [machine]);
  const isEngaged = useCallback((): boolean => isFollowing() || isAnchoring(), [isFollowing, isAnchoring]);
  const anchorIndex = useCallback((): number => {
    const authority = machine.getState().authority;
    return authority.kind === "anchoringTurn" ? authority.anchorIndex : -1;
  }, [machine]);

  // Reactive projection of "engaged" for consumers (and tests). Re-renders only
  // when the authority crosses into/out of an engaged phase — not on the
  // per-frame pin-to-bottom scrolls, which keep the authority at `following`.
  const isEngagedValue = useSyncExternalStore(machine.subscribe, isEngaged);

  // "At the bottom", derived from the phase plus the last sampled geometry (see
  // projectAtBottom). `atBottom()` is the synchronous read used by the layout
  // effects (the machine is current the instant a dispatch runs); isAtBottom is
  // the reactive value handed to the jump-to-bottom button and the dot rail.
  const atBottom = useCallback((): boolean => projectAtBottom(machine.getState()), [machine]);
  const isAtBottom = useSyncExternalStore(machine.subscribe, atBottom);

  // Suppress the jump-to-bottom button between message send and response arrival.
  const [isJumpSuppressed, setIsJumpSuppressed] = useState(false);

  // Track the last user message index to detect new user messages.
  const prevLastUserMessageIndexRef = useRef(lastUserMessageIndex);

  // Track scroll direction so REENGAGE_THRESHOLD only fires when the user
  // deliberately scrolls back to the bottom (not when they scroll up and
  // land within 5px).  -1 = uninitialized (no direction info yet).
  const prevScrollTopRef = useRef(-1);

  // Synchronous ref mirrors of isStreaming and isSuppressed, read by the scroll
  // handler and effects so they can make decisions without stale closures.
  const isStreamingRef = useRef(isStreaming);
  const isSuppressedRef = useRef(isSuppressed);
  // Mirror the latest isStreaming/isSuppressed into refs in a layout effect so
  // the write happens after commit (never during render).  Declared before the
  // other layout effects below so the mirrors are current before any of them
  // read these refs in the same commit.
  useLayoutEffect(() => {
    isStreamingRef.current = isStreaming;
    isSuppressedRef.current = isSuppressed;
  });

  // Track whether the user is actively scrolling via input devices (wheel,
  // touch, keyboard).  Only user-initiated scrolls can engage or disengage
  // auto-scroll.  Programmatic scrolls (TanStack Virtual's internal
  // measurement-correction loop, scrollToIndex, etc.) fire `scroll` events
  // but never `wheel`/`touch`/`keydown`, so they are ignored.
  const isUserScrollingRef = useRef(false);
  const userScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      // Disengage immediately on any user wheel/touch/keydown input — before any
      // scroll event fires.  The ResizeObserver fires on every content growth
      // during streaming, sets isProgrammaticScroll, and calls scrollToIndex.  If
      // the user's resulting scroll event then sees isProgrammaticScroll=true it
      // gets consumed as "programmatic" and scroll-lock is never released.
      // Dropping to userControlled here short-circuits that race: once the
      // machine is no longer `following` the ResizeObserver returns early and
      // stops scrolling.  Skip during the anchoring (filling) phase — leaving it
      // tears down the CSS animation, handled by the leave-anchoring subscription.
      // (Wheel/touch are also handled by the machine's own listener; dispatching
      // again is an idempotent no-op, and this adds keydown coverage.)
      if (!isSuppressedRef.current && isFollowing()) {
        machine.dispatch({ kind: "userScrolled" });
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
  }, [scrollContainerRef, markUserScrolling, machine, isFollowing]);

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

      const distance = distanceFromContentBottom(el, virtualizer);
      // Sample at-bottness for the projection. projectAtBottom applies the
      // anchoring/following phase override, so no special-case guard is needed.
      machine.setGeometryAtBottom(distance <= BOTTOM_THRESHOLD);

      if (isProgrammaticScroll.current) {
        isProgrammaticScroll.current = false;
        return;
      }

      if (isSuppressed) return;

      // Ignore non-user scrolls (TanStack corrections, ResizeObserver, etc.)
      if (!isUserScrollingRef.current) return;

      // A user scroll while following/anchoring hands control back to the user.
      // (Wheel/touch already did this via the machine's own listener; this
      // covers the keyboard-driven scroll path. Leaving the anchoring phase
      // tears down its animation via the leave-anchoring subscription.)
      if (isEngaged()) {
        machine.dispatch({ kind: "userScrolled" });
      } else if (isStreamingRef.current && isScrollingDown && distance <= REENGAGE_THRESHOLD) {
        // User scrolled back to the very bottom during streaming — re-engage.
        // Requires isScrollingDown so this never fires when the user is
        // scrolling UP: without the guard, a tiny upward scroll (< 5px) from
        // the absolute bottom would immediately re-engage after the wheel
        // handler disengaged, negating the user's intent.
        machine.dispatch({ kind: "reachedBottom" });
      }
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return (): void => el.removeEventListener("scroll", handleScroll);
  }, [scrollContainerRef, isSuppressed, virtualizer, isProgrammaticScroll, machine, isEngaged]);

  // Reset auto-scroll state on task switch.  Without this, stale state from
  // the previous agent leaks into the new agent's first render — e.g. a stale
  // at-bottom sample from agent A causes pin-to-bottom to fire for agent B,
  // and a higher lastUserMessageIndex triggers a spurious scroll-to-top
  // animation.  This effect MUST be declared before scroll-to-top and
  // pin-to-bottom so it runs first in the layout-effect queue.
  const prevAutoScrollTaskRef = useRef(taskId);
  useLayoutEffect(() => {
    if (prevAutoScrollTaskRef.current !== taskId) {
      prevAutoScrollTaskRef.current = taskId;
      prevLastUserMessageIndexRef.current = lastUserMessageIndex;
      // Sample "not at bottom" so pin-to-bottom can't fire for the incoming task
      // before its saved position is restored. A restore that lands at the
      // bottom re-samples true via the resulting scroll event.
      machine.setGeometryAtBottom(false);
      prevScrollTopRef.current = -1;
      // The authority (following/anchoring) is reset by the machine's
      // taskSwitched -> restoring transition (dispatched by the persistence
      // hook); this effect only resets auto-scroll's own observations and
      // tears down any in-flight scroll-to-top animation.
      clearScrollAnimation(scrollContainerRef.current, scrollAnimationRef, virtualizer, savedScrollAdjustRef);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // Transition side-effects that don't belong to any single event site:
  //  - leaving the anchoring (filling) phase tears down its scroll-to-top
  //    animation and clears jump suppression, however we left it (user scroll,
  //    overflow into following, streaming stop, or a task switch);
  //  - when a restore settles into userControlled on a still-streaming task
  //    whose restored view sits at the bottom, re-engage following (the
  //    streaming-start engage effect was a no-op while we were `restoring`).
  useEffect(() => {
    let prev = machine.getState().authority;
    return machine.subscribe(() => {
      const next = machine.getState().authority;
      // Advance the tracker before any dispatch below: re-engage dispatches
      // reachedBottom, which notifies this same subscriber re-entrantly, so the
      // tracker must already reflect `next` to stay in sync.
      const previous = prev;
      prev = next;
      if (previous.kind === "anchoringTurn" && next.kind !== "anchoringTurn") {
        clearScrollAnimation(scrollContainerRef.current, scrollAnimationRef, virtualizer, savedScrollAdjustRef);
        setIsJumpSuppressed(false);
      }

      if (previous.kind === "restoring" && next.kind === "userControlled" && isStreamingRef.current) {
        const el = scrollContainerRef.current;
        if (el !== null && distanceFromContentBottom(el, virtualizer) <= BOTTOM_THRESHOLD) {
          machine.dispatch({ kind: "reachedBottom" });
        }
      }
    });
  }, [machine, scrollContainerRef, virtualizer]);

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
    prevLastUserMessageIndexRef.current = lastUserMessageIndex;

    if (!isNewUserMessage || messageCount === 0 || isSuppressed) return;
    if (lastUserMessageIndex < 0) return;

    // For the first user message, skip the scroll-to-top animation so the
    // chat intro stays visible — but still enter filling phase so the first turn
    // follows the same anchoring → overflow → pin-to-bottom path as every later
    // turn, rather than a separate streaming-start distance check.
    if (lastUserMessageIndex === 0) {
      // Enter the anchoring (filling) phase anchored on the first message.
      // anchoringTurn projects "not at bottom", so there is no flag to flip.
      machine.dispatch({ kind: "newUserTurn", index: 0 });
      // eslint-disable-next-line react-hooks/set-state-in-effect -- genuine scroll sync: jump suppression must flip atomically with entering the anchoring phase on the new-user-message transition; not derivable during render.
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

    isProgrammaticScroll.current = true;

    // Enter the anchoring (filling) phase anchored on the new user message.
    // anchoringTurn projects "not at bottom", so the pin-to-bottom effect that
    // runs later in this same commit reads the machine and skips — no flag to set.
    machine.dispatch({ kind: "newUserTurn", index: lastUserMessageIndex });
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
  }, [
    lastUserMessageIndex,
    messageCount,
    isSuppressed,
    virtualizer,
    scrollContainerRef,
    isProgrammaticScroll,
    machine,
  ]);

  // Pin-to-bottom: when a new non-user message arrives while the user is at the
  // bottom, scroll to show it immediately (before streaming even starts). Skips
  // for user messages (scroll-to-top handles those) and while anchoring a turn
  // (projectAtBottom returns false there, so the gate below bails).
  useLayoutEffect(() => {
    if (messageCount === 0 || isSuppressed) return;
    // Read the projection live off the machine, not the rendered isAtBottom: the
    // scroll-to-top effect above runs earlier in this same commit and may have
    // just entered anchoringTurn, and the scroll handler samples geometry
    // synchronously — so this never acts on a stale value.
    if (!atBottom()) return;
    if (lastMessageRole === ChatMessageRole.USER) return;
    virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
  }, [messageCount, isAtBottom, isSuppressed, virtualizer, lastMessageRole, atBottom]);

  // Engage when streaming starts while at bottom; disengage when streaming stops.
  // Reads the live scroll position rather than the isAtBottom state, which can be
  // stale when a new user message grew the content between the last scroll event
  // and streaming starting.  Uses isSuppressedRef so the closure always sees the
  // latest value without needing isSuppressed in the dependency array.
  useEffect(() => {
    if (isStreaming && !isSuppressedRef.current) {
      // Don't re-engage via distance check while anchoring — the scroll-to-top
      // effect already entered the anchoring phase.
      if (!isAnchoring()) {
        const el = scrollContainerRef.current;
        if (el && distanceFromContentBottom(el, virtualizer) <= BOTTOM_THRESHOLD) {
          machine.dispatch({ kind: "reachedBottom" });
        }
      }
    } else if (!isStreaming) {
      // Final scroll-to-bottom before disengaging: the ResizeObserver
      // disconnects when streaming stops, so later virtualizer re-measurements
      // won't be compensated. A single scrollToIndex anchors the view at the
      // bottom before those adjustments land. Skip while anchoring (a short
      // response that never overflowed — only `following` was pinned here) and
      // when already at the very bottom (liveDistance ≤ 1px), where re-firing
      // would cause a visible jump if paddingEnd changed in the same render.
      // messageCount/virtualizer are read from the closure intentionally: this
      // branch only matters on the isStreaming transition.
      if (isFollowing() && messageCount > 0) {
        const el = scrollContainerRef.current;
        const liveDistance = el ? distanceFromContentBottom(el, virtualizer) : 0;
        if (liveDistance > 1) {
          isProgrammaticScroll.current = true;
          virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
        }
      }
      // Streaming stopped: leave following/anchoring for userControlled. The
      // leave-anchoring subscription tears down the animation and jump
      // suppression if we were anchoring. A short response that fit the viewport
      // was sampled at-bottom by the ResizeObserver (paddingEnd excluded), so
      // projectAtBottom resolves correctly without an imperative mark.
      machine.dispatch({ kind: "streamingStopped" });
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
    if (isStreaming && !prevStreamingForSuppressRef.current && !isAnchoring()) {
      setIsJumpSuppressed(false);
    }
    prevStreamingForSuppressRef.current = isStreaming;
  }, [isStreaming, isAnchoring]);

  // Streaming ResizeObserver: single observer handles both at-bottom sampling
  // and auto-scroll.  A single observer avoids redundant DOM reads — both tasks
  // need the same `distance` calculation on every content resize.
  //
  // At-bottom sampling: records the latest at-bottness into the machine so the
  // "jump to bottom" button appears as soon as the bottom goes out of sight (no
  // scroll event needed).
  //
  // Auto-scroll: when engaged, scrolls to bottom on content growth.  Reads the
  // engaged/anchoring phase from the machine (via stable getters) rather than
  // from the dep array, so the observer is not torn down and recreated on every
  // engage/disengage or anchoring transition.
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

      // Re-sample at-bottness on every content resize so the jump-to-bottom
      // button tracks the bottom going out of sight without a scroll event.
      // projectAtBottom applies the anchoring/following phase override.
      const distance = distanceFromContentBottom(el, virtualizer);
      machine.setGeometryAtBottom(distance <= BOTTOM_THRESHOLD);

      // Auto-scroll logic — only when engaged (following or anchoring) with messages.
      if (!isEngaged() || messageCount === 0) return;

      if (isAnchoring()) {
        // Only check for overflow when the response has started arriving
        // (items exist after the anchor).  The user message itself may be
        // taller than the viewport — that's not an overflow of the response.
        const anchorIdx = anchorIndex();
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
          // Response has overflowed — transition from anchoring to following.
          // The leave-anchoring subscription clears jump suppression and the
          // scroll-to-top animation.
          isProgrammaticScroll.current = true;
          machine.dispatch({ kind: "turnAnchored" });
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
        machine.dispatch({ kind: "userScrolled" });
        return;
      }
      isProgrammaticScroll.current = true;
      virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
    });

    // Initial scroll when engaging — skip while anchoring (scroll-to-top
    // already positioned the viewport).
    if (isFollowing() && messageCount > 0) {
      const liveDistance = distanceFromContentBottom(el, virtualizer);
      if (liveDistance <= BOTTOM_THRESHOLD) {
        isProgrammaticScroll.current = true;
        virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
      }
    }

    observer.observe(content);
    return (): void => observer.disconnect();
  }, [
    isStreaming,
    isSuppressed,
    messageCount,
    virtualizer,
    scrollContainerRef,
    isProgrammaticScroll,
    machine,
    isEngaged,
    isAnchoring,
    anchorIndex,
    isFollowing,
  ]);

  const scrollToBottom = useCallback((): void => {
    if (messageCount === 0) return;
    isProgrammaticScroll.current = true;
    virtualizer.scrollToIndex(messageCount - 1, { align: "end" });
    // scrollToIndex(align:"end") lands at the content bottom; record it so the
    // jump-to-bottom button hides immediately even if the resulting scroll event
    // is async or coalesced (a non-streaming jump has no other trigger).
    machine.setGeometryAtBottom(true);
    if (isStreaming) {
      // Follow the stream (also exits anchoring → following).
      machine.dispatch({ kind: "reachedBottom" });
    } else if (machine.getState().authority.kind === "anchoringTurn") {
      // Not streaming but anchored: the user explicitly went to the bottom, so
      // end the anchored turn. The leave-anchoring subscription clears jump
      // suppression.
      machine.dispatch({ kind: "userScrolled" });
    }
  }, [messageCount, virtualizer, isStreaming, isProgrammaticScroll, machine]);

  const scrollToTop = useCallback((): void => {
    if (messageCount === 0) return;
    isProgrammaticScroll.current = true;
    virtualizer.scrollToIndex(0, { align: "start" });
    // Jumped to the top — record "not at bottom" so the button shows without
    // waiting on the async scroll event, and hand control back to the user
    // (exits following/anchoring; the leave-anchoring subscription clears jump
    // suppression).
    machine.setGeometryAtBottom(false);
    machine.dispatch({ kind: "userScrolled" });
  }, [messageCount, virtualizer, isProgrammaticScroll, machine]);

  return {
    isEngaged: isEngagedValue,
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
