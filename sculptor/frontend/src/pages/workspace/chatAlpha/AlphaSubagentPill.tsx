import { Popover } from "@radix-ui/themes";
import { ChevronRightIcon, CornerDownRightIcon } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/chatAlpha/utils/subagentTree.ts";

import styles from "./AlphaSubagentPill.module.scss";
import { AlphaSubagentPopover } from "./AlphaSubagentPopover.tsx";
import { formatDuration } from "./durationUtils.ts";
import { useCloseOnChatScroll } from "./hooks/useChatScroll.tsx";
import { usePillHoverDelay } from "./hooks/usePillHoverDelay.ts";
import { ANIMATION_POOL, pickAnimationIndex } from "./pillAnimations";
import { useToolNavigation } from "./ToolNavigationContext.tsx";
import { useElapsedTime } from "./useElapsedTime.ts";

type AlphaSubagentPillProps = {
  parentBlock: ToolUseBlock;
  childNodes: Array<SubagentTreeNode>;
  toolResultMap: Map<string, ToolResultBlock>;
  subagentMetadataMap?: Map<string, SubagentMetadata>;
  /** Index assigned by parent for shared keyboard navigation. Optional — if
   *  omitted, the pill behaves as a standalone trigger with local open state. */
  rowIndex?: number;
};

export const AlphaSubagentPill = ({
  parentBlock,
  childNodes,
  toolResultMap,
  subagentMetadataMap,
  rowIndex,
}: AlphaSubagentPillProps): ReactElement => {
  const nav = useToolNavigation();
  // Shared-nav wiring is opt-in via rowIndex. When omitted, fall back to
  // local open/pinned state so the pill works standalone (e.g. in stories
  // or as a non-registered child).
  const sharedNav = nav !== null && rowIndex !== undefined ? nav : null;

  // Local open/pinned state — used when this pill isn't wired into a
  // shared ToolNavigationProvider. The pinned flag mirrors the tool-pill /
  // chip-row pattern: click pins (hover-leave can't dismiss), hover opens
  // unpinned (hover-leave dismisses after the close-delay window).
  // eslint-disable-next-line react/hook-use-state
  const [isLocalOpen, setIsLocalOpenState] = useState(false);
  const localIsPinnedRef = useRef(false);
  const setLocalOpenPillId = useCallback((id: string | null, pinned: boolean = true): void => {
    localIsPinnedRef.current = id !== null && pinned;
    setIsLocalOpenState(id !== null);
  }, []);

  const isOpen = sharedNav ? sharedNav.openItemId === parentBlock.id : isLocalOpen;
  const openItemId = sharedNav ? sharedNav.openItemId : isLocalOpen ? parentBlock.id : null;
  const setOpenPillId = sharedNav ? sharedNav.setOpenItemId : setLocalOpenPillId;
  const isPinnedRef = sharedNav ? sharedNav.isPinnedRef : localIsPinnedRef;

  const popoverContentRef = useRef<HTMLDivElement | null>(null);

  const {
    handlePillMouseEnter,
    handlePillMouseLeave,
    handlePopoverMouseEnter,
    handlePopoverMouseLeave,
    notifyPinnedToggle,
  } = usePillHoverDelay({
    openPillId: openItemId,
    setOpenPillId,
    isPinnedRef,
    popoverElRef: popoverContentRef,
  });

  const setOpen = useCallback(
    (open: boolean): void => {
      setOpenPillId(open ? parentBlock.id : null, true);
      notifyPinnedToggle(open);
    },
    [setOpenPillId, parentBlock.id, notifyPinnedToggle],
  );

  const triggerRef = useRef<HTMLButtonElement>(null);

  // Register this single-item row so arrow-key navigation can land on it.
  useEffect(() => {
    if (!nav || rowIndex === undefined) return;
    nav.registerRow(rowIndex, [parentBlock.id]);
    return (): void => nav.unregisterRow(rowIndex);
  }, [nav, rowIndex, parentBlock.id]);

  useEffect(() => {
    if (!nav) return;
    nav.setItemRef(parentBlock.id, triggerRef.current);
    return (): void => nav.setItemRef(parentBlock.id, null);
  }, [nav, parentBlock.id]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLButtonElement>): void => {
      if (!nav) return;
      // Arrows only step the open popover. When the pill is focused but
      // closed, let the event propagate so the global prompt-nav listener
      // can handle it (matching AlphaToolPillRow's behavior). stopPropagation
      // keeps the chat from scrolling when we own the key.
      switch (e.key) {
        case "ArrowRight":
        case "ArrowLeft": {
          if (!isOpen) break;
          e.preventDefault();
          e.stopPropagation();
          nav.navigate(e.key === "ArrowRight" ? "next" : "prev", parentBlock.id);
          break;
        }

        case "ArrowUp":
        case "ArrowDown": {
          if (!isOpen) break;
          e.preventDefault();
          e.stopPropagation();
          nav.navigate(e.key === "ArrowUp" ? "up" : "down", parentBlock.id);
          break;
        }

        case "Escape": {
          if (isOpen) {
            e.preventDefault();
            setOpen(false);
            triggerRef.current?.focus();
          }
          break;
        }
      }
    },
    [nav, isOpen, setOpen, parentBlock.id],
  );

  // Dismiss on chat scroll — the popover's anchor (this pill) has moved,
  // so the floating panel no longer points at it.
  const handleCloseOnScroll = useCallback((): void => setOpen(false), [setOpen]);
  useCloseOnChatScroll(handleCloseOnScroll, isOpen);

  // Pick a stable animation index once per mount. Lazy useState keeps the
  // choice constant across re-renders while remaining safe to read in render;
  // the value never changes after mount, so there is no setter.
  // eslint-disable-next-line react/hook-use-state
  const [animationIndex] = useState(pickAnimationIndex);

  const metadata = subagentMetadataMap?.get(parentBlock.id);
  const result = toolResultMap.get(parentBlock.id);
  // Background Agent tool_uses (run_in_background=true) get an immediate
  // "Async agent launched" tool_result that completes in ~0s — that's the
  // launch ack, not the subagent finishing. For background pills, treat the
  // arrival of responseText (derived from the subagent's child messages) as
  // the completion signal, and ignore the launch-ack's durationSeconds.
  const isBackground = metadata?.isBackground === true;
  const isThinking = isBackground ? !metadata?.responseText : !metadata?.responseText && !result;

  // Timer: always ticking while thinking, frozen once complete
  const { elapsed } = useElapsedTime(true, isThinking, parentBlock.id);
  const elapsedSeconds = parseFloat(elapsed);
  const completedDuration = isBackground
    ? (metadata?.durationSeconds ?? elapsedSeconds)
    : (result?.durationSeconds ?? elapsedSeconds);
  const duration = formatDuration(isThinking ? elapsedSeconds : completedDuration);

  const ThinkingAnimation = ANIMATION_POOL[animationIndex];

  const pillClassName = `${styles.pill}${isOpen ? ` ${styles.pillOpen}` : ""}`;

  return (
    <Popover.Root open={isOpen} onOpenChange={setOpen}>
      <div className={styles.row}>
        <span className={styles.gutterIcon}>
          {isThinking ? <ThinkingAnimation /> : <CornerDownRightIcon size={14} />}
        </span>
        {/* Hover zone wraps the pill so the hit-area can extend slightly past
            the visible button — same pattern AlphaToolPillRow uses — and so
            hover-leave fires reliably when the cursor heads toward the popover. */}
        <span
          className={styles.pillHoverZone}
          onMouseEnter={() => handlePillMouseEnter(parentBlock.id)}
          onMouseLeave={(e) => handlePillMouseLeave(e)}
        >
          <Popover.Trigger className={styles.trigger}>
            <button
              ref={triggerRef}
              className={pillClassName}
              data-testid={ElementIds.ALPHA_CHAT_SUBAGENT_PILL}
              onKeyDown={handleKeyDown}
            >
              {metadata?.prompt && <span className={styles.pillPrompt}>{metadata.prompt}</span>}
              <span className={styles.pillDuration}>{duration}</span>
              <ChevronRightIcon size={14} className={`${styles.chevron}${isOpen ? ` ${styles.chevronOpen}` : ""}`} />
            </button>
          </Popover.Trigger>
        </span>
      </div>
      <Popover.Content
        ref={popoverContentRef}
        side="bottom"
        sideOffset={4}
        align="start"
        collisionPadding={16}
        className={styles.popoverContent}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onFocusOutside={(e) => e.preventDefault()}
        onMouseEnter={handlePopoverMouseEnter}
        onMouseLeave={handlePopoverMouseLeave}
      >
        <AlphaSubagentPopover
          parentBlock={parentBlock}
          childNodes={childNodes}
          toolResultMap={toolResultMap}
          metadata={metadata}
          isThinking={isThinking}
        />
      </Popover.Content>
    </Popover.Root>
  );
};
