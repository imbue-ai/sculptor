import { useStore } from "jotai";
import { type ReactElement, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { isSidebarDragActiveAtom } from "~/components/nav/navAtoms.ts";

import styles from "./WorkspacePeekOverlay.module.scss";
import { WorkspacePeekPopover } from "./WorkspacePeekPopover";

// The peek opens instantly on hover (no hover-intent delay).
const OPEN_DELAY_MS = 0;
const CLOSE_DELAY_MS = 80;
// Gap in pixels between the sidebar's edge and the peek overlay.
const PEEK_OFFSET_PX = 4;

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
  const overlayRef = useRef<HTMLDivElement>(null);
  // Sorting a sidebar row/group sweeps the pointer across other rows; keep the
  // peek closed for the whole drag. Tracked in a ref (same reason as
  // isVisibleRef, and the overlay needn't re-render on drag start/end) — the
  // effect below keeps it in sync via a store subscription.
  const isSidebarDragActiveRef = useRef(false);
  const store = useStore();

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
    // Workspace rows live in the left sidebar, so the peek anchors just past the
    // sidebar's right edge (level with the hovered row's top) rather than below
    // it. Anchor to the sidebar container, not the row itself: the row's right
    // edge shifts inward as its hover-action icons appear/hide, and the sidebar
    // is resizable — deriving x from the sidebar edge keeps the peek flush
    // against it no matter the width.
    const rowRect = tabElement.getBoundingClientRect();
    const sidebar = tabElement.closest(`[data-testid="${ElementIds.WORKSPACE_SIDEBAR}"]`);
    const anchorRight = sidebar ? sidebar.getBoundingClientRect().right : rowRect.right;
    setPosition({ x: anchorRight + PEEK_OFFSET_PX, y: rowRect.top });
  }, []);

  const dismiss = useCallback((): void => {
    clearTimers();
    isVisibleRef.current = false;
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
      if (isSidebarDragActiveRef.current) return;
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
        // Not visible — schedule the open.
        activeTabIdRef.current = workspaceId;
        updatePosition(tab);
        openTimerRef.current = setTimeout(() => {
          setHoveredWorkspaceId(workspaceId);
          isVisibleRef.current = true;
          setIsVisible(true);
          // Enable transitions only after initial position is set
          requestAnimationFrame(() => setHasAnimated(true));
        }, OPEN_DELAY_MS);
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

    // A drag starting dismisses an already-open peek; handleMouseOver keeps it
    // closed for the rest of the drag via the ref.
    isSidebarDragActiveRef.current = store.get(isSidebarDragActiveAtom);
    const unsubscribeDrag = store.sub(isSidebarDragActiveAtom, () => {
      isSidebarDragActiveRef.current = store.get(isSidebarDragActiveAtom);
      if (isSidebarDragActiveRef.current) {
        dismiss();
      }
    });

    document.addEventListener("mouseover", handleMouseOver);
    document.addEventListener("mouseout", handleMouseOut);
    document.addEventListener("click", handleClick, true);
    document.addEventListener("auxclick", handleClick, true);
    return (): void => {
      unsubscribeDrag();
      document.removeEventListener("mouseover", handleMouseOver);
      document.removeEventListener("mouseout", handleMouseOut);
      document.removeEventListener("click", handleClick, true);
      document.removeEventListener("auxclick", handleClick, true);
    };
  }, [clearTimers, scheduleClose, dismiss, getWorkspaceTabId, updatePosition, store]);

  // Cleanup timers on unmount
  useEffect(() => clearTimers, [clearTimers]);

  // Clamp the overlay so a row hovered low in the sidebar doesn't push the
  // popover past the viewport bottom. `position.y` anchors to the hovered
  // row's top; measuring the rendered height (which depends on the popover's
  // content, up to its max-height) lets us shift a tall popover up just enough
  // to keep it fully on screen. Runs in a layout effect so the correction lands
  // before paint, and only writes back when clamping actually moves it so the
  // measure/clamp loop settles after one adjustment.
  useLayoutEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    const maxY = window.innerHeight - overlay.offsetHeight - PEEK_OFFSET_PX;
    const clampedY = Math.max(PEEK_OFFSET_PX, Math.min(position.y, maxY));
    if (clampedY !== position.y) {
      setPosition((prev) => ({ ...prev, y: clampedY }));
    }
  }, [position.y]);

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
      ref={overlayRef}
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
