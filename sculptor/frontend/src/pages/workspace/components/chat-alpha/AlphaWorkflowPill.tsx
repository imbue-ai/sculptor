import { Popover } from "@radix-ui/themes";
import { ChevronRightIcon, CornerDownRightIcon } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ToolResultBlock, ToolUseBlock, WorkflowTaskState } from "~/api";
import { ElementIds } from "~/api";
import { useCurrentTaskWorkflowStates } from "~/common/state/hooks/useTaskDetail";

// Shares the subagent pill's stylesheet so workflows read as the same kind
// of chat object — full-width accent pill with a gutter icon and duration.
import styles from "./AlphaSubagentPill.module.scss";
import popoverStyles from "./AlphaWorkflowPopover.module.scss";
import { AlphaWorkflowPopover } from "./AlphaWorkflowPopover.tsx";
import { useCloseOnChatScroll } from "./hooks/useChatScroll.tsx";
import { usePillHoverDelay } from "./hooks/usePillHoverDelay.ts";
import { ANIMATION_POOL, pickAnimationIndex } from "./pill-animations";
import { useToolNavigation } from "./ToolNavigationContext.tsx";
import { useElapsedTime } from "./useElapsedTime.ts";
import { countWorkflowAgents, getWorkflowDisplayName } from "./workflowEntries.ts";
import { formatWorkflowDuration } from "./workflowFormat.ts";

type AlphaWorkflowPillProps = {
  toolUseId: string;
  /** Present unless the finalized message result-replaced the tool_use. */
  block?: ToolUseBlock;
  /** The launch acknowledgement result, when available. */
  result?: ToolResultBlock;
  /** Index assigned by parent for shared keyboard navigation. Optional — if
   *  omitted, the pill behaves as a standalone trigger with local open state. */
  rowIndex?: number;
};

const buildPillText = (state: WorkflowTaskState | undefined, displayName: string): string => {
  if (!state) return `Workflow ${displayName}`;
  const { doneCount, totalCount, activePhaseTitle } = countWorkflowAgents(state);
  if (state.status === "running") {
    const phasePart = activePhaseTitle ? `${activePhaseTitle} · ` : "";
    return `Workflow ${displayName} — ${phasePart}${doneCount}/${totalCount} agents`;
  }
  if (state.status === "failed") return `Workflow ${displayName} — failed`;
  if (state.status === "stopped") return `Workflow ${displayName} — stopped`;
  return `Workflow ${displayName} — ${totalCount} ${totalCount === 1 ? "agent" : "agents"}`;
};

export const AlphaWorkflowPill = ({ toolUseId, block, result, rowIndex }: AlphaWorkflowPillProps): ReactElement => {
  const nav = useToolNavigation();
  const sharedNav = nav !== null && rowIndex !== undefined ? nav : null;

  // Local open/pinned state — used when this pill isn't wired into a shared
  // ToolNavigationProvider. Mirrors AlphaSubagentPill.
  // eslint-disable-next-line react/hook-use-state
  const [isLocalOpen, setIsLocalOpenState] = useState(false);
  const localIsPinnedRef = useRef(false);
  const setLocalOpenPillId = useCallback((id: string | null, pinned: boolean = true): void => {
    localIsPinnedRef.current = id !== null && pinned;
    setIsLocalOpenState(id !== null);
  }, []);

  const isOpen = sharedNav ? sharedNav.openItemId === toolUseId : isLocalOpen;
  const openItemId = sharedNav ? sharedNav.openItemId : isLocalOpen ? toolUseId : null;
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
      setOpenPillId(open ? toolUseId : null, true);
      notifyPinnedToggle(open);
    },
    [setOpenPillId, toolUseId, notifyPinnedToggle],
  );

  const triggerRef = useRef<HTMLDivElement>(null);

  // Register this single-item row so arrow-key navigation can land on it.
  useEffect(() => {
    if (!nav || rowIndex === undefined) return;
    nav.registerRow(rowIndex, [toolUseId]);
    return (): void => nav.unregisterRow(rowIndex);
  }, [nav, rowIndex, toolUseId]);

  useEffect(() => {
    if (!nav) return;
    nav.setItemRef(toolUseId, triggerRef.current);
    return (): void => nav.setItemRef(toolUseId, null);
  }, [nav, toolUseId]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      // The trigger is a div[role=button] (not a real button), so Enter/Space
      // activation is handled here rather than natively.
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(!isOpen);
        return;
      }
      if (!nav) return;
      switch (e.key) {
        case "ArrowRight":
        case "ArrowLeft": {
          if (!isOpen) break;
          e.preventDefault();
          e.stopPropagation();
          nav.navigate(e.key === "ArrowRight" ? "next" : "prev", toolUseId);
          break;
        }

        case "ArrowUp":
        case "ArrowDown": {
          if (!isOpen) break;
          e.preventDefault();
          e.stopPropagation();
          nav.navigate(e.key === "ArrowUp" ? "up" : "down", toolUseId);
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
    [nav, isOpen, setOpen, toolUseId],
  );

  const handleCloseOnScroll = useCallback((): void => setOpen(false), [setOpen]);
  useCloseOnChatScroll(handleCloseOnScroll, isOpen);

  // eslint-disable-next-line react/hook-use-state
  const [animationIndex] = useState(pickAnimationIndex);

  const workflowStates = useCurrentTaskWorkflowStates();
  const state = workflowStates[toolUseId];
  const displayName = getWorkflowDisplayName({ state, input: block?.input });
  const isRunning = state?.status === "running";

  // Duration: the workflow's own run time from usage (updated each progress
  // tick, frozen at the final value on completion). Before the first tick,
  // fall back to a local elapsed timer so the pill isn't blank while running.
  const { elapsed } = useElapsedTime(true, isRunning, toolUseId);
  const usageDurationMs = state?.usage?.durationMs;
  const duration =
    usageDurationMs !== undefined && usageDurationMs !== null
      ? formatWorkflowDuration(usageDurationMs)
      : isRunning
        ? formatWorkflowDuration(parseFloat(elapsed) * 1000)
        : "";

  const ThinkingAnimation = ANIMATION_POOL[animationIndex];
  const pillClassName = `${styles.pill}${isOpen ? ` ${styles.pillOpen}` : ""}`;

  return (
    <Popover.Root open={isOpen} onOpenChange={setOpen}>
      <div className={styles.row}>
        <span className={styles.gutterIcon}>
          {isRunning ? <ThinkingAnimation /> : <CornerDownRightIcon size={14} />}
        </span>
        <span
          className={styles.pillHoverZone}
          onMouseEnter={() => handlePillMouseEnter(toolUseId)}
          onMouseLeave={(e) => handlePillMouseLeave(e)}
        >
          <Popover.Trigger className={styles.trigger}>
            <div
              ref={triggerRef}
              role="button"
              tabIndex={0}
              aria-expanded={isOpen}
              className={pillClassName}
              data-testid={ElementIds.ALPHA_CHAT_WORKFLOW_PILL}
              data-workflow-status={state?.status ?? "unknown"}
              onKeyDown={handleKeyDown}
            >
              <span className={styles.pillPrompt}>{buildPillText(state, displayName)}</span>
              {duration && <span className={styles.pillDuration}>{duration}</span>}
              <ChevronRightIcon size={14} className={`${styles.chevron}${isOpen ? ` ${styles.chevronOpen}` : ""}`} />
            </div>
          </Popover.Trigger>
        </span>
      </div>
      <Popover.Content
        ref={popoverContentRef}
        side="bottom"
        sideOffset={4}
        align="start"
        collisionPadding={16}
        className={popoverStyles.popoverContent}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onFocusOutside={(e) => e.preventDefault()}
        onMouseEnter={handlePopoverMouseEnter}
        onMouseLeave={handlePopoverMouseLeave}
      >
        <AlphaWorkflowPopover state={state} displayName={displayName} result={result} />
      </Popover.Content>
    </Popover.Root>
  );
};
