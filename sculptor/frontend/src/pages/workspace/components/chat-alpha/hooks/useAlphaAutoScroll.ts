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

import {
  bottomPinOffset,
  distanceFromContentBottom,
  FOOTER_REVEAL_WINDOW_MS,
  PIN_BOTTOM_GAP,
} from "../scroll/geometry.ts";
import type { ReadingAnchor } from "../scroll/scrollStateMachine.ts";
import {
  createScrollStateMachine,
  projectAtBottom,
  projectReflow,
  type ScrollStateMachine,
} from "../scroll/scrollStateMachine.ts";

const BOTTOM_THRESHOLD = 200;
// Tighter threshold for re-engaging auto-scroll. The user must scroll to
// essentially the very bottom — not just "near" it — to opt back in.
const REENGAGE_THRESHOLD = 5;
// How many px before the viewport edge to transition from filling phase to
// pin-to-bottom.  Firing early keeps the growing content from visibly
// overshooting the viewport while the ResizeObserver lags a beat behind.
// Must equal the pin gap: the anchored rest position coincides with
// bottomPinOffset exactly when the tail has filled the viewport to within
// PIN_BOTTOM_GAP of its bottom edge, so entering `following` is a zero-px
// handoff — the view is already at the pin. Any larger value starts
// `following` above the pin, in violation of its invariant, and forces an
// immediate upward correction.
const FILLING_OVERFLOW_BUFFER = PIN_BOTTOM_GAP;

// Upward pin corrections chase genuine tail shrinks (a collapsed text line
// is ~20px+), never sub-line measurement wobble.
const PIN_UPWARD_DEADBAND = 8;

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

  // Read the auto-scroll authority off the machine, wrapped in useCallback so
  // they are stable dependencies for the effects below (the machine is stable).
  const isFollowing = useCallback((): boolean => machine.getState().authority.kind === "following", [machine]);
  const isAnchoring = useCallback((): boolean => machine.getState().authority.kind === "anchoringTurn", [machine]);
  const isEngaged = useCallback((): boolean => isFollowing() || isAnchoring(), [isFollowing, isAnchoring]);

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

  // Record the reading anchor — the top-visible message and how far its own top
  // sits below the viewport top — from a scrollTop the user produced. The reflow
  // policy (projectReflow ⇒ holdAnchor) restores this exact framing after a
  // content reflow, even across the non-virtualized intro padding above the first
  // message, which per-item compensation can't see. Sampling only on genuine user
  // scrolls keeps a correction scroll during the reflow from overwriting the
  // position we are preserving.
  const captureReadingAnchor = useCallback(
    (scrollTop: number): void => {
      const items = virtualizer.getVirtualItems();
      if (items.length === 0) return;
      const topVisible = items.find((it) => it.start + it.size > scrollTop) ?? items[0];
      machine.setReadingAnchor({ messageIndex: topVisible.index, viewportOffset: topVisible.start - scrollTop });
    },
    [virtualizer, machine],
  );

  // The single "scroll to the bottom" primitive: land the content bottom
  // PIN_BOTTOM_GAP above the viewport bottom, keeping the rest of paddingEnd as
  // slack below scrollTop (see bottomPinOffset). Downward moves always apply.
  // Upward moves apply only while `following`, whose per-frame invariant IS the
  // pin gap: a mid-stream tail shrink (e.g. the standalone streaming cursor
  // collapsing into the first text line) moves the target back up, and leaving
  // scrollTop stranded past it shows oversized breathing room below the newest
  // line until growth overtakes the difference — on slow machines for long
  // enough that the pin-gap tests fail. In every other phase an upward move
  // would only chase a turn-end shrink, which we leave in place.
  const pinToBottom = useCallback((): void => {
    const el = scrollContainerRef.current;
    if (!el || messageCount === 0) return;
    const desired = bottomPinOffset(el, virtualizer);
    const isBelowTarget = desired > el.scrollTop + 1;
    const isStrandedPastTarget = isFollowing() && el.scrollTop - desired > PIN_UPWARD_DEADBAND;
    if (!isBelowTarget && !isStrandedPastTarget) return;
    isProgrammaticScroll.current = true;
    el.scrollTop = desired;
  }, [scrollContainerRef, virtualizer, messageCount, isProgrammaticScroll, isFollowing]);

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

  // Turn-footer reveal window: the timestamp (performance.now) until which the
  // content observer re-pins to the bottom after a followed turn ends, plus the
  // content height and viewport size sampled then (the reveal condition below
  // compares against both). Zeroed on user takeover.
  const revealFooterUntilRef = useRef(0);
  const revealFooterBaseHeightRef = useRef(0);
  const revealFooterViewportRef = useRef("");

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
      // A user input ends the footer-reveal window immediately: a takeover wins.
      revealFooterUntilRef.current = 0;
      // Disengage on user wheel/touch/keydown before the scroll event fires.
      // During streaming the ResizeObserver sets isProgrammaticScroll and scrolls;
      // a user scroll event that saw that flag would be consumed as programmatic
      // and never release the scroll-lock. Dropping to userControlled here
      // pre-empts that — the ResizeObserver returns early once we are no longer
      // `following`. Skip while anchoring (leaving it tears down the CSS
      // animation, handled by the leave-anchoring subscription). Wheel/touch also
      // reach the machine's own listener; this adds keydown coverage.
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

      // Remember where the user is reading so a later reflow can hold it.
      captureReadingAnchor(currentScrollTop);

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
  }, [scrollContainerRef, isSuppressed, virtualizer, isProgrammaticScroll, machine, isEngaged, captureReadingAnchor]);

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
      // Drop the outgoing task's reading anchor — its message index/offset is
      // meaningless for the incoming task. The first user scroll re-samples it.
      machine.setReadingAnchor(null);
      prevScrollTopRef.current = -1;
      // Cancel any in-flight footer-reveal window from the outgoing task.
      revealFooterUntilRef.current = 0;
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
    pinToBottom();
  }, [messageCount, isAtBottom, isSuppressed, lastMessageRole, atBottom, pinToBottom]);

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
      // Final settle onto the pinned bottom before disengaging: the ResizeObserver
      // disconnects when streaming stops, so later virtualizer re-measurements won't
      // be compensated — pin now, before they land. Skip while anchoring (a short
      // response that never overflowed).
      if (isFollowing() && messageCount > 0) {
        pinToBottom();
        // The turn footer mounts a beat later and grows the content below the fold;
        // open a short window so the content observer re-pins to reveal it at the
        // bottom, matching where focusing the input lands.
        const el = scrollContainerRef.current;
        if (el) {
          revealFooterUntilRef.current = performance.now() + FOOTER_REVEAL_WINDOW_MS;
          revealFooterBaseHeightRef.current = el.scrollHeight;
          revealFooterViewportRef.current = `${el.clientWidth}x${el.clientHeight}`;
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

  // One reflow restore in flight at a time, reading the freshest measurements.
  const reflowRestoreRafRef = useRef(0);

  // Restore the captured reading anchor after a content reflow. Runs on the next
  // frame so the virtualizer's item measurements reflect the reflowed sizes, then
  // sets scrollTop so the anchor message sits back at its sampled viewport offset.
  // Assigning scrollTop absolutely (rather than relying on TanStack's per-item
  // compensation) is what holds the anchor steady even when the non-virtualized
  // intro padding above the first message reflowed taller.
  const restoreReadingAnchor = useCallback(
    (anchor: ReadingAnchor): void => {
      cancelAnimationFrame(reflowRestoreRafRef.current);
      reflowRestoreRafRef.current = requestAnimationFrame(() => {
        reflowRestoreRafRef.current = 0;
        const el = scrollContainerRef.current;
        if (!el) return;
        // Force the measurements memo to reflect the reflowed sizes before reading.
        virtualizer.getVirtualItems();
        const item = virtualizer.measurementsCache[anchor.messageIndex];
        if (!item) return;
        const desired = Math.max(0, item.start - anchor.viewportOffset);
        if (Math.abs(el.scrollTop - desired) > 1) {
          isProgrammaticScroll.current = true;
          el.scrollTop = desired;
        }
        machine.setGeometryAtBottom(distanceFromContentBottom(el, virtualizer) <= BOTTOM_THRESHOLD);
      });
    },
    [scrollContainerRef, virtualizer, machine, isProgrammaticScroll],
  );

  // Perform the one typed reflow action projectReflow chose for the current
  // authority phase. This is the single executor the unified content observer
  // drives — projectReflow decides, applyReflow performs.
  const applyReflow = useCallback(
    (el: HTMLElement, distance: number): void => {
      const action = projectReflow(machine.getState());
      switch (action.kind) {
        case "ignore":
          return;
        case "holdAnchor":
          // Scrolled up and reading — keep the anchor message at its offset.
          restoreReadingAnchor(action.anchor);
          return;
        case "pinBottom": {
          // Following the live tail — keep the last message's content bottom in
          // view. A user actively scrolling away during a stream hands control back.
          if (distance > BOTTOM_THRESHOLD && isUserScrollingRef.current) {
            machine.dispatch({ kind: "userScrolled" });
            return;
          }
          if (messageCount === 0) return;
          pinToBottom();
          machine.setGeometryAtBottom(true);
          return;
        }

        case "holdTurn": {
          // A fresh user turn is anchored at the top while its response fills in
          // below. Do nothing until the response overflows the viewport — then
          // hand off to following. Viewport stability (shouldAdjustScrollPosition
          // in useAlphaVirtualizer) keeps the user message at the top meanwhile,
          // so we never re-anchor on each token (that produced visible jitter).
          const anchorIdx = action.anchorIndex;
          if (anchorIdx < 0 || messageCount <= anchorIdx + 1) return;
          const anchorItem = virtualizer.measurementsCache[anchorIdx];
          const anchorSize = anchorItem?.size ?? 0;
          const anchorEnd = anchorItem ? anchorItem.start + anchorSize : 0;
          const contentBottom = virtualizer.getTotalSize() - (virtualizer.options.paddingEnd ?? 0);
          const tailHeight = contentBottom - anchorEnd;
          // Compare against (clientHeight - anchorSize): the user message already
          // occupies the top portion of the viewport.
          if (tailHeight >= el.clientHeight - anchorSize - FILLING_OVERFLOW_BUFFER) {
            machine.dispatch({ kind: "turnAnchored" });
            pinToBottom();
          }
          return;
        }

        default: {
          const unreachable: never = action;
          throw new Error(`Unhandled reflow action: ${JSON.stringify(unreachable)}`);
        }
      }
    },
    [machine, virtualizer, messageCount, restoreReadingAnchor, pinToBottom],
  );

  // Unified content-resize observer. One observer, always connected while not
  // suppressed; on any content size change — a streamed token, a viewport width
  // reflow, an above-fold item growing — it samples at-bottness and applies
  // projectReflow's chosen action for the current phase.
  useLayoutEffect(() => {
    if (isSuppressed) return;
    const el = scrollContainerRef.current;
    const content = el?.firstElementChild;
    if (!el || !content) return;

    const observer = new ResizeObserver(() => {
      if (messageCount === 0) return;
      const distance = distanceFromContentBottom(el, virtualizer);
      machine.setGeometryAtBottom(distance <= BOTTOM_THRESHOLD);
      // Reveal the turn footer that grew the content just after a followed turn ended:
      // re-pin (down-only) to the grown content bottom, within the window opened at
      // streaming stop. The two non-obvious guards: still userControlled (a new turn
      // opened within the window is anchoringTurn and must not be yanked down), and an
      // unchanged viewport (a resize reflow keeps its own reading-anchor behavior).
      if (
        performance.now() < revealFooterUntilRef.current &&
        machine.getState().authority.kind === "userControlled" &&
        el.scrollHeight > revealFooterBaseHeightRef.current + 1 &&
        `${el.clientWidth}x${el.clientHeight}` === revealFooterViewportRef.current
      ) {
        pinToBottom();
      }
      applyReflow(el, distance);
    });

    // Initial pin when a stream (re)connects already pinned to the bottom —
    // covers a stream starting while the content already overflowed, where no
    // further resize would otherwise fire the pin. Only `following` yields
    // pinBottom, so idle reconnects fall through untouched.
    if (isStreaming && messageCount > 0 && projectReflow(machine.getState()).kind === "pinBottom") {
      if (distanceFromContentBottom(el, virtualizer) <= BOTTOM_THRESHOLD) {
        pinToBottom();
      }
    }

    observer.observe(content);
    return (): void => {
      observer.disconnect();
      cancelAnimationFrame(reflowRestoreRafRef.current);
    };
  }, [isStreaming, isSuppressed, messageCount, virtualizer, scrollContainerRef, machine, applyReflow, pinToBottom]);

  const scrollToBottom = useCallback((): void => {
    if (messageCount === 0) return;
    pinToBottom();
    // Record at-bottom so the jump-to-bottom button hides immediately even if the
    // resulting scroll event is async or coalesced (a non-streaming jump has no
    // other trigger).
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
  }, [messageCount, isStreaming, machine, pinToBottom]);

  const scrollToTop = useCallback((): void => {
    if (messageCount === 0) return;
    isProgrammaticScroll.current = true;
    virtualizer.scrollToIndex(0, { align: "start" });
    // Jumped to the top — record "not at bottom" so the button shows without
    // waiting on the async scroll event, and hand control back to the user
    // (exits following/anchoring; the leave-anchoring subscription clears jump
    // suppression).
    machine.setGeometryAtBottom(false);
    // Anchor reading at the first message so a subsequent reflow holds the top.
    // scrollToIndex(0, "start") lands scrollTop at ~0, so the offset is its start.
    machine.setReadingAnchor({ messageIndex: 0, viewportOffset: virtualizer.measurementsCache[0]?.start ?? 0 });
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
