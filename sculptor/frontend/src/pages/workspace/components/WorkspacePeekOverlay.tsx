import { type ReactElement, useCallback, useEffect, useRef, useState } from "react";

import styles from "./WorkspacePeekOverlay.module.scss";
import { WorkspacePeekPopover } from "./WorkspacePeekPopover";

const OPEN_DELAY_MS = 600;
const CLOSE_DELAY_MS = 80;
// After closing, re-entering a tab within this window reopens immediately.
const REOPEN_GRACE_PERIOD_MS = 300;

type OverlayPosition = {
  x: number;
  y: number;
};

type WorkspacePeekOverlayProps = {
  onNavigate: (workspaceId: string, agentId?: string) => void;
};

/**
 * A single shared popover that follows the hovered workspace tab.
 *
 * Instead of mounting a separate HoverCard per tab, this overlay listens for
 * mouseenter/leave events on workspace tabs via the data-workspace-tab attribute and
 * smoothly animates its position when the user moves between tabs.
 */
export const WorkspacePeekOverlay = ({ onNavigate }: WorkspacePeekOverlayProps): ReactElement | null => {
  const [hoveredWorkspaceId, setHoveredWorkspaceId] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [position, setPosition] = useState<OverlayPosition>({ x: 0, y: 0 });
  const [hasAnimated, setHasAnimated] = useState(false);

  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isOverPopoverRef = useRef(false);
  const isOverTabRef = useRef(false);
  const activeTabIdRef = useRef<string | null>(null);
  // Track visibility in a ref so event listeners don't need to be re-registered
  // when visibility changes (which would cause missed mouseout events).
  const isVisibleRef = useRef(false);
  const lastClosedAtRef = useRef(0);

  const clearTimers = useCallback((): void => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }

    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const updatePosition = useCallback((tabElement: Element): void => {
    // When the tab is inside a dropdown menu (overflow), position the peek to
    // the right of the dropdown so it doesn't overlap the menu.
    const dropdownContent = tabElement.closest("[role='menu']");
    if (dropdownContent) {
      const menuRect = dropdownContent.getBoundingClientRect();
      setPosition({ x: menuRect.right + 4, y: menuRect.top });
    } else {
      const rect = tabElement.getBoundingClientRect();
      setPosition({ x: rect.left, y: rect.bottom + 4 });
    }
  }, []);

  const dismiss = useCallback((): void => {
    clearTimers();
    isVisibleRef.current = false;
    lastClosedAtRef.current = Date.now();
    setIsVisible(false);
    setHoveredWorkspaceId(null);
    setHasAnimated(false);
    activeTabIdRef.current = null;
  }, [clearTimers]);

  const scheduleClose = useCallback((): void => {
    clearTimers();
    closeTimerRef.current = setTimeout(() => {
      if (!isOverPopoverRef.current && !isOverTabRef.current) {
        dismiss();
      }
    }, CLOSE_DELAY_MS);
  }, [clearTimers, dismiss]);

  const getWorkspaceTabId = useCallback((target: EventTarget | null): string | null => {
    if (!target) return null;
    const element = target as HTMLElement;
    const tab = element.closest?.("[data-workspace-tab]");
    if (!tab) return null;
    return tab.getAttribute("data-tab-id");
  }, []);

  // Listen for mouse events on workspace tabs using event delegation.
  // This effect intentionally avoids depending on isVisible (using isVisibleRef
  // instead) so that listeners are never torn down/recreated on visibility
  // changes, which would cause missed mouseout events.
  useEffect((): (() => void) => {
    const handleMouseOver = (e: MouseEvent): void => {
      const workspaceId = getWorkspaceTabId(e.target);
      if (!workspaceId) return;

      isOverTabRef.current = true;
      clearTimers();

      const tab = (e.target as HTMLElement).closest(`[data-tab-id="${workspaceId}"]`);
      if (!tab) return;

      if (isVisibleRef.current && activeTabIdRef.current !== workspaceId) {
        // Already visible — instantly switch content, animate position
        setHoveredWorkspaceId(workspaceId);
        updatePosition(tab);
        activeTabIdRef.current = workspaceId;
      } else if (!isVisibleRef.current) {
        // Not visible — open immediately if within grace period, otherwise delay
        activeTabIdRef.current = workspaceId;
        updatePosition(tab);
        const timeSinceClose = Date.now() - lastClosedAtRef.current;
        const delay = timeSinceClose < REOPEN_GRACE_PERIOD_MS ? 0 : OPEN_DELAY_MS;
        openTimerRef.current = setTimeout(() => {
          setHoveredWorkspaceId(workspaceId);
          isVisibleRef.current = true;
          setIsVisible(true);
          // Enable transitions only after initial position is set
          requestAnimationFrame(() => setHasAnimated(true));
        }, delay);
      }
    };

    const handleMouseOut = (e: MouseEvent): void => {
      const fromTab = getWorkspaceTabId(e.target);
      const toTab = getWorkspaceTabId(e.relatedTarget);
      if (fromTab && !toTab) {
        isOverTabRef.current = false;
        scheduleClose();
      }
    };

    // Dismiss the popover immediately when a tab is clicked (left or middle)
    // so it doesn't obscure the workspace the user just navigated to.
    // Middle-click fires "auxclick" (not "click"), so we must listen for both.
    const handleClick = (e: MouseEvent): void => {
      if (getWorkspaceTabId(e.target)) {
        dismiss();
      }
    };

    document.addEventListener("mouseover", handleMouseOver);
    document.addEventListener("mouseout", handleMouseOut);
    document.addEventListener("click", handleClick, true);
    document.addEventListener("auxclick", handleClick, true);
    return (): void => {
      document.removeEventListener("mouseover", handleMouseOver);
      document.removeEventListener("mouseout", handleMouseOut);
      document.removeEventListener("click", handleClick, true);
      document.removeEventListener("auxclick", handleClick, true);
    };
  }, [clearTimers, scheduleClose, dismiss, getWorkspaceTabId, updatePosition]);

  // Cleanup timers on unmount
  useEffect(() => clearTimers, [clearTimers]);

  const handlePopoverMouseEnter = useCallback((): void => {
    isOverPopoverRef.current = true;
    clearTimers();
  }, [clearTimers]);

  const handlePopoverMouseLeave = useCallback((): void => {
    isOverPopoverRef.current = false;
    scheduleClose();
  }, [scheduleClose]);

  if (!isVisible || hoveredWorkspaceId == null) return null;

  return (
    <div
      className={`${styles.overlay} ${hasAnimated ? styles.animated : ""}`}
      style={{ transform: `translate(${position.x}px, ${position.y}px)` }}
      onMouseEnter={handlePopoverMouseEnter}
      onMouseLeave={handlePopoverMouseLeave}
      data-testid="workspace-peek-overlay"
    >
      <WorkspacePeekPopover workspaceId={hoveredWorkspaceId} onNavigate={onNavigate} onDismiss={dismiss} />
    </div>
  );
};
