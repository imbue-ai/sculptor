import { Anchor as PopoverAnchor } from "@radix-ui/react-popover";
import { Popover } from "@radix-ui/themes";
import type { CSSProperties, KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";

import type { ChipDiffPopoverActions } from "./AlphaChipDiffPopover.tsx";
import { AlphaChipDiffPopover } from "./AlphaChipDiffPopover.tsx";
import styles from "./AlphaChipRow.module.scss";
import { AlphaFileChip } from "./AlphaFileChip.tsx";
import { buildChipData } from "./chipRowUtils.ts";
import { useCloseOnChatScroll } from "./hooks/useChatScroll.tsx";
import { usePillHoverDelay } from "./hooks/usePillHoverDelay.ts";
import { useToolNavigation } from "./ToolNavigationContext.tsx";

const POPOVER_STYLE: CSSProperties = {
  padding: 0,
  width: 560,
  // Cap to the viewport so the popover never overflows a narrow (mobile) screen.
  // Desktop is unaffected: 560px is far below the cap on any normal window.
  maxWidth: "calc(100vw - 24px)",
  maxHeight: 380,
};

type AlphaChipRowProps = {
  blocks: ReadonlyArray<ToolUseBlock>;
  toolResultMap: Map<string, ToolResultBlock>;
  inProgressMessageId: string | null;
  rowIndex?: number;
};

export const AlphaChipRow = ({
  blocks,
  toolResultMap,
  inProgressMessageId,
  rowIndex,
}: AlphaChipRowProps): ReactElement | null => {
  const nav = useToolNavigation();

  // Local state — used only when no ToolNavigationProvider wraps this row.
  // Mirrors AlphaToolPillRow: the setter is wrapped to keep localIsPinnedRef
  // in lock-step with the open id so hover-delay state stays consistent.
  // eslint-disable-next-line react/hook-use-state
  const [localOpenChipId, setLocalOpenChipIdState] = useState<string | null>(null);
  const localIsPinnedRef = useRef(false);
  const setLocalOpenChipId = useCallback((id: string | null, pinned: boolean = true): void => {
    localIsPinnedRef.current = id !== null && pinned;
    setLocalOpenChipIdState(id);
  }, []);
  const openChipId = nav ? nav.openItemId : localOpenChipId;
  const setOpenChipId = nav ? nav.setOpenItemId : setLocalOpenChipId;
  const isPinnedRef = nav ? nav.isPinnedRef : localIsPinnedRef;

  const [rawFocusedIndex, setRawFocusedIndex] = useState(0);
  const chipRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const chipRowRef = useRef<HTMLDivElement>(null);
  const popoverActionRef = useRef<ChipDiffPopoverActions | null>(null);
  const popoverContentRef = useRef<HTMLDivElement | null>(null);

  const {
    handlePillMouseEnter,
    handlePillMouseLeave,
    handlePopoverMouseEnter,
    handlePopoverMouseLeave,
    notifyPinnedToggle,
  } = usePillHoverDelay({
    openPillId: openChipId,
    setOpenPillId: setOpenChipId,
    isPinnedRef,
    popoverElRef: popoverContentRef,
  });

  const chipDataList = useMemo(
    () => buildChipData(blocks, toolResultMap, inProgressMessageId),
    [blocks, toolResultMap, inProgressMessageId],
  );

  // Register this row's chips with the shared context.
  useEffect(() => {
    if (!nav || rowIndex === undefined) return;
    const chipIds = chipDataList.map((c) => c.id);
    nav.registerRow(rowIndex, chipIds);
    return (): void => {
      nav.unregisterRow(rowIndex);
    };
  }, [nav, rowIndex, chipDataList]);

  // Clamp focusedIndex inline instead of via effect to avoid an extra render cycle
  const focusedIndex = chipDataList.length > 0 ? Math.min(rawFocusedIndex, chipDataList.length - 1) : 0;

  // Does this row own the currently open chip?
  const openChip = openChipId ? chipDataList.find((c) => c.id === openChipId) : undefined;
  const isPopoverOpen = openChip !== undefined;

  /**
   * Navigate the open popover to an adjacent chip within this row and scroll
   * it into view.  Only used when no shared context is available (standalone).
   */
  const localNavigateToChip = useCallback(
    (targetIndex: number): void => {
      const chip = chipDataList[targetIndex];
      if (!chip) return;

      setOpenChipId(chip.id);
      setRawFocusedIndex(targetIndex);

      chipRefs.current[targetIndex]?.scrollIntoView({ block: "nearest", inline: "nearest" });
    },
    [chipDataList, setOpenChipId],
  );

  const handleNavigate = useCallback(
    (direction: "prev" | "next" | "up" | "down"): void => {
      // Delegate to the shared context if available — it handles cross-row navigation.
      if (nav) {
        nav.navigate(direction);
        return;
      }

      // Fallback: navigate within this row only. Vertical nav has no
      // sibling row to jump to outside the shared context.
      if (direction === "up" || direction === "down") return;

      const currentIndex = openChipId ? chipDataList.findIndex((c) => c.id === openChipId) : focusedIndex;
      const targetIndex =
        direction === "prev" ? Math.max(currentIndex - 1, 0) : Math.min(currentIndex + 1, chipDataList.length - 1);
      if (targetIndex === currentIndex) return;
      localNavigateToChip(targetIndex);
    },
    [nav, openChipId, chipDataList, focusedIndex, localNavigateToChip],
  );

  const handleToggle = useCallback(
    (chipId: string, open: boolean): void => {
      setOpenChipId(open ? chipId : null, true);
      notifyPinnedToggle(open);
    },
    [setOpenChipId, notifyPinnedToggle],
  );

  // Dismiss on chat scroll: the chip anchor has moved and the floating
  // diff panel no longer points at anything the user is looking at.
  const handleCloseOnScroll = useCallback((): void => {
    setOpenChipId(null, false);
    notifyPinnedToggle(false);
  }, [setOpenChipId, notifyPinnedToggle]);
  useCloseOnChatScroll(handleCloseOnScroll, isPopoverOpen);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      switch (e.key) {
        case "ArrowRight": {
          e.preventDefault();
          if (isPopoverOpen) {
            handleNavigate("next");
          } else {
            const next = Math.min(focusedIndex + 1, chipDataList.length - 1);
            setRawFocusedIndex(next);
            chipRefs.current[next]?.focus();
          }
          break;
        }

        case "ArrowLeft": {
          e.preventDefault();
          if (isPopoverOpen) {
            handleNavigate("prev");
          } else {
            const prev = Math.max(focusedIndex - 1, 0);
            setRawFocusedIndex(prev);
            chipRefs.current[prev]?.focus();
          }
          break;
        }

        case "ArrowUp":
        case "ArrowDown": {
          // Only intercept while a popover is open. stopPropagation prevents
          // the window-level prompt-nav listener from also handling the key
          // and scrolling the chat.
          if (!isPopoverOpen) break;
          e.preventDefault();
          e.stopPropagation();
          handleNavigate(e.key === "ArrowUp" ? "up" : "down");
          break;
        }

        case "Enter": {
          if (e.shiftKey && isPopoverOpen) {
            e.preventDefault();
            popoverActionRef.current?.openDiffPanel();
          }
          break;
        }

        case "Escape": {
          e.preventDefault();
          setOpenChipId(null);
          chipRefs.current[focusedIndex]?.focus();
          break;
        }
      }
    },
    [focusedIndex, chipDataList.length, isPopoverOpen, handleNavigate, setOpenChipId],
  );

  if (chipDataList.length === 0) return null;

  return (
    <div className={styles.chipRowWrapper}>
      <Popover.Root
        open={isPopoverOpen}
        onOpenChange={(open) => {
          if (!open) setOpenChipId(null);
        }}
      >
        <PopoverAnchor>
          <div
            ref={chipRowRef}
            className={styles.chipRow}
            role="toolbar"
            aria-label="File modifications"
            onKeyDown={handleKeyDown}
            data-testid={ElementIds.ALPHA_CHAT_CHIP_ROW}
          >
            {chipDataList.map((chip, index) => (
              // Hover zone wraps each chip so the hit-area extends past
              // the visible button. Adjacent zones touch, so sliding
              // across the row keeps the popover open continuously —
              // same pattern AlphaToolPillRow uses for tool pills.
              <span
                key={chip.id}
                className={styles.chipHoverZone}
                onMouseEnter={() => handlePillMouseEnter(chip.id)}
                onMouseLeave={(e) => handlePillMouseLeave(e)}
              >
                <AlphaFileChip
                  ref={(el) => {
                    chipRefs.current[index] = el;
                    nav?.setItemRef(chip.id, el);
                  }}
                  chipData={chip}
                  isOpen={openChipId === chip.id}
                  onToggle={() => handleToggle(chip.id, openChipId !== chip.id)}
                  onFocus={() => setRawFocusedIndex(index)}
                  tabIndex={index === focusedIndex ? 0 : -1}
                />
              </span>
            ))}
          </div>
        </PopoverAnchor>
        <Popover.Content
          side="bottom"
          sideOffset={4}
          align="start"
          collisionPadding={16}
          className={styles.popoverContent}
          onOpenAutoFocus={(e) => e.preventDefault()}
          onFocusOutside={(e) => e.preventDefault()}
          onPointerDownOutside={(e) => {
            if (chipRowRef.current?.contains(e.target as Node)) e.preventDefault();
          }}
          style={POPOVER_STYLE}
        >
          {openChip && (
            <div ref={popoverContentRef} onMouseEnter={handlePopoverMouseEnter} onMouseLeave={handlePopoverMouseLeave}>
              <AlphaChipDiffPopover
                chipData={openChip}
                onClose={() => setOpenChipId(null)}
                onNavigate={handleNavigate}
                actionRef={popoverActionRef}
              />
            </div>
          )}
        </Popover.Content>
      </Popover.Root>
    </div>
  );
};
