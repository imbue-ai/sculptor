import { ContextMenu, IconButton } from "@radix-ui/themes";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ReactElement, RefObject } from "react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage, TextBlock } from "~/api";
import { MarkdownBlock } from "~/components/MarkdownBlock";
import type { BlockUnion } from "~/pages/workspace/utils/blockGuards.ts";
import { isTextBlock } from "~/pages/workspace/utils/blockGuards.ts";
import { stripHtml } from "~/pages/workspace/utils/stripHtml.ts";

import styles from "./PromptNavigator.module.scss";

// The collapsed indicator takes roughly one dot-slot worth of space, so we
// can show maxVisibleDots − 1 actual dots when collapsing (plus the indicator).
const MIN_VISIBLE_DOTS = 5;

// Approximate pixel heights for computing how many dots fit.
const DOT_HEIGHT_PX = 7;
const RAIL_FIXED_OVERHEAD_PX = 15;
const DEFAULT_MAX_VISIBLE_DOTS = 30;

// Popover hover timing — mirrors WorkspacePeekOverlay.
const OPEN_DELAY_MS = 420;
const CLOSE_DELAY_MS = 80;
const REOPEN_GRACE_PERIOD_MS = 300;

// How long the copy button shows its "copied" checkmark before reverting.
const COPY_FEEDBACK_DURATION_MS = 1500;

const getMessageText = (message: ChatMessage): string =>
  message.content
    .filter((block: BlockUnion): block is TextBlock => isTextBlock(block))
    .map((block) => stripHtml(block.text))
    .join("");

type PopoverPosition = {
  x: number;
  y: number;
};

type PromptNavigatorProps = {
  /** User messages in conversation order, used for dot count and tooltip text. */
  userMessages: ReadonlyArray<ChatMessage>;
  /** Scroll container ref, used to compute how many dots fit vertically. */
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  /** Index of the currently active user prompt (0-based into userMessages). */
  activePromptIndex: number;
  /** Called when navigating to a prompt. promptIndex is in [0, userMessages.length). */
  onNavigate: (promptIndex: number) => void;
};

export const PromptNavigator = ({
  userMessages,
  scrollContainerRef,
  activePromptIndex,
  onNavigate,
}: PromptNavigatorProps): ReactElement | null => {
  const [isContextMenuOpen, setIsContextMenuOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const railRef = useRef<HTMLDivElement>(null);
  const [maxVisibleDots, setMaxVisibleDots] = useState(DEFAULT_MAX_VISIBLE_DOTS);
  const prevDotCountRef = useRef(userMessages.length);

  // FLIP-style compensation: when a new dot is added to the bottom-anchored
  // rail, all dots shift up.  We remember the rail's top edge from the previous
  // commit, then apply a compensating translateY to cancel the visual jump,
  // and let the CSS transition slide dots to their new positions.
  const prevRailTopRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    const rail = railRef.current;
    const prevTop = prevRailTopRef.current;
    const prevCount = prevDotCountRef.current;
    const newCount = userMessages.length;
    prevDotCountRef.current = newCount;

    if (!rail) {
      prevRailTopRef.current = null;
      return;
    }

    // Measure the rail's top after this commit. The ref still holds the top
    // measured in the previous layout effect (before the new dot existed), so
    // the difference tells us how far the rail shifted.
    const newTop = rail.getBoundingClientRect().top;
    prevRailTopRef.current = newTop;

    if (newCount <= prevCount || prevTop == null) return;

    const offset = prevTop - newTop;
    if (offset <= 0) return;

    // Cancel any in-progress transition and snap to the compensating offset.
    rail.style.transition = "none";
    rail.style.transform = `translateY(${offset}px)`;

    // Next frame: re-enable the transition and animate back to 0.
    requestAnimationFrame(() => {
      rail.style.transition = "";
      rail.style.transform = "";
    });
    // maxVisibleDots is included so a resize-driven re-layout refreshes the
    // stored top (without triggering compensation, since the count is unchanged),
    // keeping the FLIP baseline accurate when the next dot is added.
  }, [userMessages.length, maxVisibleDots]);

  // Popover state — mirrors WorkspacePeekOverlay pattern.
  const [popoverIndex, setPopoverIndex] = useState<number | null>(null);
  const [isPopoverVisible, setIsPopoverVisible] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState<PopoverPosition>({ x: 0, y: 0 });
  const [hasAnimated, setHasAnimated] = useState(false);

  // Tracks which prompt was last copied. Deriving the "copied" indicator from
  // this (rather than a bare boolean) means it naturally clears when the user
  // hovers a different dot — no effect needed to reset on dot change.
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const popoverRef = useRef<HTMLDivElement>(null);
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isOverPopoverRef = useRef(false);
  const isOverDotRef = useRef(false);
  const isPopoverVisibleRef = useRef(false);
  const lastClosedAtRef = useRef(0);
  const activeDotIndexRef = useRef<number | null>(null);

  const clearOpenTimer = useCallback((): void => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
  }, []);

  const clearCloseTimer = useCallback((): void => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const clearPopoverTimers = useCallback((): void => {
    clearOpenTimer();
    clearCloseTimer();
  }, [clearOpenTimer, clearCloseTimer]);

  const dismissPopover = useCallback((): void => {
    clearPopoverTimers();
    isPopoverVisibleRef.current = false;
    lastClosedAtRef.current = Date.now();
    setIsPopoverVisible(false);
    setPopoverIndex(null);
    setHasAnimated(false);
    activeDotIndexRef.current = null;
  }, [clearPopoverTimers]);

  // Clear only the close timer — preserve the open timer so that moving the
  // mouse between dots doesn't restart the open delay on each dot. The open
  // timer is cancelled only when the close timer actually fires and confirms
  // the user has left the rail.
  const schedulePopoverClose = useCallback((): void => {
    clearCloseTimer();
    closeTimerRef.current = setTimeout(() => {
      if (!isOverPopoverRef.current && !isOverDotRef.current) {
        clearOpenTimer();
        dismissPopover();
      }
    }, CLOSE_DELAY_MS);
  }, [clearCloseTimer, clearOpenTimer, dismissPopover]);

  const updatePopoverPosition = useCallback((dotElement: HTMLElement): void => {
    const rect = dotElement.getBoundingClientRect();
    setPopoverPosition({ x: rect.right, y: rect.top + rect.height / 2 });
  }, []);

  const handleDotMouseEnter = useCallback(
    (messageIndex: number, dotElement: HTMLElement): void => {
      if (isContextMenuOpen) return;
      isOverDotRef.current = true;
      clearCloseTimer();

      if (isPopoverVisibleRef.current && activeDotIndexRef.current !== messageIndex) {
        // Already visible — instantly switch content, animate position.
        setPopoverIndex(messageIndex);
        updatePopoverPosition(dotElement);
        activeDotIndexRef.current = messageIndex;
      } else if (!isPopoverVisibleRef.current) {
        // Retarget the pending open to this dot. If a timer is already running
        // from a previous dot, let it finish — it reads activeDotIndexRef when
        // it fires, so cumulative hover across dots opens for whichever dot
        // the mouse is on at that moment.
        activeDotIndexRef.current = messageIndex;
        updatePopoverPosition(dotElement);
        if (openTimerRef.current === null) {
          const timeSinceClose = Date.now() - lastClosedAtRef.current;
          const delay = timeSinceClose < REOPEN_GRACE_PERIOD_MS ? 0 : OPEN_DELAY_MS;
          openTimerRef.current = setTimeout(() => {
            openTimerRef.current = null;
            const targetIndex = activeDotIndexRef.current;
            if (targetIndex === null || !isOverDotRef.current) return;
            setPopoverIndex(targetIndex);
            isPopoverVisibleRef.current = true;
            setIsPopoverVisible(true);
            requestAnimationFrame(() => setHasAnimated(true));
          }, delay);
        }
      }
    },
    [clearCloseTimer, updatePopoverPosition, isContextMenuOpen],
  );

  const handleDotMouseLeave = useCallback((): void => {
    isOverDotRef.current = false;
    schedulePopoverClose();
  }, [schedulePopoverClose]);

  const handlePopoverMouseEnter = useCallback((): void => {
    isOverPopoverRef.current = true;
    clearPopoverTimers();
  }, [clearPopoverTimers]);

  const handlePopoverMouseLeave = useCallback((): void => {
    isOverPopoverRef.current = false;
    schedulePopoverClose();
  }, [schedulePopoverClose]);

  const handleContextMenuOpenChange = useCallback(
    (open: boolean): void => {
      setIsContextMenuOpen(open);
      // Dismiss the popover when the context menu opens so the two don't overlap.
      if (open) dismissPopover();
    },
    [dismissPopover],
  );

  const handlePopoverCopy = useCallback((): void => {
    if (popoverIndex == null) return;
    const message = userMessages[popoverIndex];
    if (!message) return;
    void navigator.clipboard.writeText(getMessageText(message));
    setCopiedIndex(popoverIndex);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopiedIndex(null), COPY_FEEDBACK_DURATION_MS);
  }, [popoverIndex, userMessages]);

  // Cleanup timers on unmount.
  useEffect(() => {
    return (): void => {
      clearPopoverTimers();
      clearTimeout(copyTimerRef.current);
    };
  }, [clearPopoverTimers]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height ?? 0;
      const availableDotSpace = height - RAIL_FIXED_OVERHEAD_PX;
      const dots = Math.max(MIN_VISIBLE_DOTS, Math.floor(availableDotSpace / DOT_HEIGHT_PX));
      setMaxVisibleDots(dots);
    });
    observer.observe(container);
    return (): void => observer.disconnect();
  }, [scrollContainerRef]);

  useEffect(() => {
    if (!isExpanded) return;
    const handleClickOutside = (event: MouseEvent): void => {
      if (railRef.current && !railRef.current.contains(event.target as Node)) {
        setIsExpanded(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return (): void => document.removeEventListener("mousedown", handleClickOutside);
  }, [isExpanded]);

  const shouldCollapse = userMessages.length > maxVisibleDots;
  const dotsToShow = shouldCollapse ? maxVisibleDots - 1 : userMessages.length;
  const headCount = Math.ceil(dotsToShow / 2);
  const tailCount = dotsToShow - headCount;
  const collapsedCount = shouldCollapse ? userMessages.length - headCount - tailCount : 0;

  const visibleIndices = useMemo((): ReadonlyArray<number> => {
    const count = userMessages.length;
    if (!shouldCollapse || isExpanded) {
      return Array.from({ length: count }, (_, i) => i);
    }
    const head = Array.from({ length: headCount }, (_, i) => i);
    const tail = Array.from({ length: tailCount }, (_, i) => count - tailCount + i);
    return [...head, ...tail];
  }, [userMessages.length, shouldCollapse, isExpanded, headCount, tailCount]);

  const popoverMessage = popoverIndex != null ? userMessages[popoverIndex] : null;
  // Cache the popover body so unrelated re-renders (popover-position updates,
  // dot hover changes, FLIP compensation) don't re-stringify the message and
  // force MarkdownBlock to re-parse its identical input. Must sit above the
  // early-return below to keep hook order stable.
  const popoverContent = useMemo(
    () => (popoverMessage != null ? getMessageText(popoverMessage) : ""),
    [popoverMessage],
  );

  // The checkmark shows only for the prompt that was just copied; switching
  // dots changes popoverIndex and clears it automatically.
  const isCopied = copiedIndex != null && copiedIndex === popoverIndex;

  if (userMessages.length === 0) return null;

  const renderDot = (messageIndex: number): ReactElement => {
    const message = userMessages[messageIndex]!;
    const isActive = messageIndex === activePromptIndex;
    const isPopoverTarget = isPopoverVisible && messageIndex === popoverIndex;
    return (
      <ContextMenu.Root key={message.id} onOpenChange={handleContextMenuOpenChange}>
        <ContextMenu.Trigger>
          <div
            className={styles.dotWrapper}
            onClick={() => onNavigate(messageIndex)}
            onMouseEnter={(e) => handleDotMouseEnter(messageIndex, e.currentTarget)}
            onMouseLeave={handleDotMouseLeave}
            role="button"
            tabIndex={0}
            aria-label={`Go to prompt ${messageIndex + 1}`}
          >
            <div
              className={`${styles.dot} ${isActive || isPopoverTarget ? styles.dotActive : ""}`}
              data-testid="ALPHA_PROMPT_NAVIGATOR_DOT"
              data-is-active={isActive ? "true" : "false"}
            />
          </div>
        </ContextMenu.Trigger>
        <ContextMenu.Content size="1">
          <ContextMenu.Item onSelect={() => void navigator.clipboard.writeText(getMessageText(message))}>
            Copy prompt
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Root>
    );
  };

  return (
    <>
      <div
        className={`${styles.rail} ${isPopoverVisible ? styles.railPopoverOpen : ""}`}
        data-testid="ALPHA_PROMPT_NAVIGATOR_RAIL"
        ref={railRef}
      >
        {shouldCollapse && !isExpanded ? (
          <>
            {visibleIndices.slice(0, headCount).map(renderDot)}
            <div
              className={`${styles.collapsedIndicator} ${styles.collapsedIndicatorClickable}`}
              data-testid="ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR"
              aria-label={`${collapsedCount} prompts hidden, click to expand`}
              role="button"
              tabIndex={0}
              onClick={() => setIsExpanded(true)}
            >
              +{collapsedCount}
            </div>
            {visibleIndices.slice(headCount).map(renderDot)}
          </>
        ) : (
          visibleIndices.map(renderDot)
        )}
      </div>
      {isPopoverVisible && popoverMessage != null && popoverIndex != null && (
        <div
          ref={popoverRef}
          className={`${styles.popoverHitArea} ${hasAnimated ? styles.popoverAnimated : ""}`}
          style={{ transform: `translate(${popoverPosition.x}px, ${popoverPosition.y}px)` }}
          onMouseEnter={handlePopoverMouseEnter}
          onMouseLeave={handlePopoverMouseLeave}
        >
          <div className={styles.popover} data-testid="ALPHA_PROMPT_NAVIGATOR_TOOLTIP">
            <div className={styles.popoverHeader}>
              <div className={styles.popoverLabel}>PROMPT {popoverIndex + 1}</div>
              <IconButton
                variant="ghost"
                size="1"
                className={styles.popoverCopyButton}
                onClick={handlePopoverCopy}
                title="Copy prompt"
                data-testid="ALPHA_PROMPT_NAVIGATOR_COPY_BUTTON"
              >
                {isCopied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
              </IconButton>
            </div>
            <div className={styles.popoverText}>
              <MarkdownBlock content={popoverContent} />
            </div>
          </div>
        </div>
      )}
    </>
  );
};
