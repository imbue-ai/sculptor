import type { MouseEvent as ReactMouseEvent } from "react";
import { useCallback, useEffect, useRef } from "react";

// Mirrors WorkspacePeekOverlay's hover-delay timing.
const OPEN_DELAY_MS = 600;
const CLOSE_DELAY_MS = 80;
// After closing, re-entering a pill within this window reopens immediately.
const REOPEN_GRACE_PERIOD_MS = 300;
// Idle-timeout for the safe-triangle hold: if the cursor stops moving inside
// the polygon for this long without ever reaching the popover, fall back to
// the simple close path. The timer resets on every in-polygon mousemove, so a
// user who's actively traversing toward the popover (even slowly) stays held.
const SAFE_AREA_IDLE_MS = 1200;
// Pad the popover rect when building the safe area so the user's cursor
// has wiggle room near the visible edge — the polygon should fully cover
// the gap between trigger and popover plus a buffer for hand jitter.
const SAFE_AREA_PADDING_PX = 32;

type Point = { x: number; y: number };

// Ray-cast point-in-polygon. Works for any simple polygon.
const isPointInPolygon = (point: Point, polygon: ReadonlyArray<Point>): boolean => {
  let isInside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i]!;
    const b = polygon[j]!;
    const doesIntersect =
      a.y > point.y !== b.y > point.y && point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x;
    if (doesIntersect) isInside = !isInside;
  }
  return isInside;
};

const paddedCorners = (rect: DOMRect, pad: number): Array<Point> => [
  { x: rect.left - pad, y: rect.top - pad },
  { x: rect.right + pad, y: rect.top - pad },
  { x: rect.right + pad, y: rect.bottom + pad },
  { x: rect.left - pad, y: rect.bottom + pad },
];

// Andrew's monotone-chain convex hull. Sorting by angle around the centroid
// silently fails when one of the input points is interior to the others —
// the resulting polygon becomes non-convex and excludes a wedge near the
// interior point. Computing the actual hull avoids that whole class of bug,
// which matters here because the cursor's exit point sits very close to the
// padded popover edge (with only sideOffset=4 between trigger and popover).
const convexHull = (input: ReadonlyArray<Point>): Array<Point> => {
  if (input.length < 3) return [...input];
  const points = [...input].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (o: Point, a: Point, b: Point): number => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower: Array<Point> = [];
  for (const p of points) {
    while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: Array<Point> = [];
  for (let i = points.length - 1; i >= 0; i--) {
    const p = points[i]!;
    while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, p) <= 0) upper.pop();
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
};

// "Safe area" is the convex hull of the trigger, the popover, and a box
// around the cursor's exit point — all padded. Treating the exit point as
// a box (rather than a single point) is what gives the user room to
// overshoot past the popover edge on the way to an action button: the
// hull extends at least SAFE_AREA_PADDING_PX past where the cursor left.
const buildSafeArea = (exit: Point, popoverRect: DOMRect, triggerRect: DOMRect | null): ReadonlyArray<Point> => {
  const pad = SAFE_AREA_PADDING_PX;
  const exitBox = new DOMRect(exit.x, exit.y, 0, 0);
  const points: Array<Point> = [...paddedCorners(exitBox, pad), ...paddedCorners(popoverRect, pad)];
  if (triggerRect) points.push(...paddedCorners(triggerRect, pad));
  return convexHull(points);
};

type UsePillHoverDelayParams = {
  openPillId: string | null;
  setOpenPillId: (id: string | null, pinned?: boolean) => void;
  isPinnedRef: React.MutableRefObject<boolean>;
  /**
   * Optional ref to the popover content element. When provided, leaving the
   * pill while the popover is open arms a "safe triangle": close only fires
   * once the cursor exits the polygon between the exit point and the popover
   * rect (or after SAFE_AREA_IDLE_MS of no in-polygon motion as a fallback).
   * This lets the user move the pointer diagonally toward the popover —
   * including into its action buttons — without the popover dismissing
   * mid-traversal.
   */
  popoverElRef?: React.MutableRefObject<HTMLElement | null>;
};

type UsePillHoverDelayReturn = {
  handlePillMouseEnter: (pillId: string) => void;
  handlePillMouseLeave: (event?: ReactMouseEvent) => void;
  handlePopoverMouseEnter: () => void;
  handlePopoverMouseLeave: (event?: ReactMouseEvent) => void;
  /** Call after a click pins/unpins the pill so hover bookkeeping stays consistent. */
  notifyPinnedToggle: (open: boolean) => void;
};

/**
 * Encapsulates the open/close timer state machine that drives hover-triggered
 * pill popovers. Mirrors WorkspacePeekOverlay's behavior:
 *  - hovering a pill opens after `OPEN_DELAY_MS` (or instantly within the
 *    re-open grace window after a recent close)
 *  - leaving the pill or popover closes after `CLOSE_DELAY_MS`
 *  - while one popover is already open and unpinned, sliding to a sibling
 *    pill switches immediately
 *  - a pinned pill (opened via click/keyboard) ignores hover-leave dismissal
 */
export const usePillHoverDelay = ({
  openPillId,
  setOpenPillId,
  isPinnedRef,
  popoverElRef,
}: UsePillHoverDelayParams): UsePillHoverDelayReturn => {
  // Refs (not state) so transitioning hover across pills doesn't re-render or
  // re-register listeners.
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Cleanup for whatever close path is currently armed: either the simple
  // 80ms timeout (popover-leave) or the safe-area tracker (pill-leave with a
  // popover el available). Unified so cancellation has a single entry point.
  const closeCleanupRef = useRef<(() => void) | null>(null);
  const isOverPopoverRef = useRef(false);
  const isOverPillRef = useRef(false);
  const lastClosedAtRef = useRef(0);
  const pendingHoverPillIdRef = useRef<string | null>(null);

  const cancelClose = useCallback((): void => {
    if (closeCleanupRef.current) {
      closeCleanupRef.current();
      closeCleanupRef.current = null;
    }
  }, []);

  const clearTimers = useCallback((): void => {
    if (openTimerRef.current) {
      clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
    cancelClose();
  }, [cancelClose]);

  useEffect(() => clearTimers, [clearTimers]);

  const fireClose = useCallback((): void => {
    closeCleanupRef.current = null;
    if (isPinnedRef.current) return;
    if (isOverPopoverRef.current || isOverPillRef.current) return;
    pendingHoverPillIdRef.current = null;
    lastClosedAtRef.current = Date.now();
    setOpenPillId(null, false);
  }, [setOpenPillId, isPinnedRef]);

  const armSimpleCloseTimer = useCallback((): void => {
    const timer = setTimeout(() => {
      closeCleanupRef.current = null;
      fireClose();
    }, CLOSE_DELAY_MS);
    closeCleanupRef.current = (): void => clearTimeout(timer);
  }, [fireClose]);

  const scheduleClose = useCallback(
    (exitPoint?: Point | null, triggerRect?: DOMRect | null): void => {
      cancelClose();

      const popoverEl = popoverElRef?.current ?? null;
      const popoverRect = popoverEl?.getBoundingClientRect();
      // Safe-area path: arm a global pointer-tracker so the popover doesn't
      // dismiss while the user moves toward its action buttons. Skip if we
      // don't have what we need to build a meaningful polygon (no exit
      // point, no popover el, or a zero-sized rect — which can happen
      // before the portal has laid out).
      if (exitPoint && popoverRect && popoverRect.width > 0 && popoverRect.height > 0) {
        const polygon = buildSafeArea(exitPoint, popoverRect, triggerRect ?? null);

        // Pending close (armed once the cursor first exits the safe area).
        // Kept inside the tracker so a re-entry can cancel it without
        // touching closeCleanupRef.
        let pendingTimer: ReturnType<typeof setTimeout> | null = null;
        const clearPendingTimer = (): void => {
          if (pendingTimer !== null) {
            clearTimeout(pendingTimer);
            pendingTimer = null;
          }
        };

        let idleTimer: ReturnType<typeof setTimeout> | null = null;
        const armIdleTimer = (): void => {
          if (idleTimer !== null) clearTimeout(idleTimer);
          idleTimer = setTimeout(finishClose, SAFE_AREA_IDLE_MS);
        };

        const cleanupTracker = (): void => {
          document.removeEventListener("mousemove", onMove);
          if (idleTimer !== null) clearTimeout(idleTimer);
          clearPendingTimer();
        };

        const finishClose = (): void => {
          cleanupTracker();
          if (closeCleanupRef.current === cleanupTracker) closeCleanupRef.current = null;
          fireClose();
        };

        const onMove = (e: MouseEvent): void => {
          const isInside = isPointInPolygon({ x: e.clientX, y: e.clientY }, polygon);
          if (isInside) {
            // Re-entering the safe area cancels any pending close from a
            // prior excursion — pointer jitter shouldn't dismiss the popover.
            clearPendingTimer();
            // Active motion inside the polygon resets the idle ceiling, so a
            // slow but moving traversal toward the popover stays held.
            armIdleTimer();
            return;
          }

          if (pendingTimer === null) {
            pendingTimer = setTimeout(finishClose, CLOSE_DELAY_MS);
          }
        };

        // Idle ceiling: if no mousemove arrives inside the polygon within
        // SAFE_AREA_IDLE_MS, give up. Reset on every in-polygon mousemove.
        armIdleTimer();

        document.addEventListener("mousemove", onMove);
        closeCleanupRef.current = cleanupTracker;
        return;
      }

      armSimpleCloseTimer();
    },
    [cancelClose, fireClose, popoverElRef, armSimpleCloseTimer],
  );

  const handlePillMouseEnter = useCallback(
    (pillId: string): void => {
      isOverPillRef.current = true;
      cancelClose();

      // Already open on this pill — nothing to do.
      if (openPillId === pillId) {
        if (openTimerRef.current) {
          clearTimeout(openTimerRef.current);
          openTimerRef.current = null;
        }
        return;
      }

      // Pinned to a different pill — let the user see the pinned popover.
      // They can click another pill to switch the pin.
      if (isPinnedRef.current && openPillId !== null) return;

      // Popover already open (and not pinned to another pill) — switch instantly.
      if (openPillId !== null) {
        if (openTimerRef.current) {
          clearTimeout(openTimerRef.current);
          openTimerRef.current = null;
        }
        pendingHoverPillIdRef.current = pillId;
        setOpenPillId(pillId, false);
        return;
      }

      // Not open — schedule open after delay (or instant within grace period).
      if (openTimerRef.current) clearTimeout(openTimerRef.current);
      pendingHoverPillIdRef.current = pillId;
      const timeSinceClose = Date.now() - lastClosedAtRef.current;
      const delay = timeSinceClose < REOPEN_GRACE_PERIOD_MS ? 0 : OPEN_DELAY_MS;
      openTimerRef.current = setTimeout(() => {
        openTimerRef.current = null;
        if (pendingHoverPillIdRef.current !== pillId) return;
        setOpenPillId(pillId, false);
      }, delay);
    },
    [openPillId, setOpenPillId, isPinnedRef, cancelClose],
  );

  const handlePillMouseLeave = useCallback(
    (event?: ReactMouseEvent): void => {
      isOverPillRef.current = false;
      // Cancel any pending hover-open so the popover doesn't pop after we leave.
      if (openTimerRef.current) {
        clearTimeout(openTimerRef.current);
        openTimerRef.current = null;
      }
      pendingHoverPillIdRef.current = null;
      const exit = event ? { x: event.clientX, y: event.clientY } : null;
      // `currentTarget` is the element the handler is bound to (the pill's
      // hover zone), regardless of which child the pointer actually left
      // through. Its rect goes into the safe-area hull so the trigger side
      // is covered too, not just the popover side.
      const triggerEl = event?.currentTarget instanceof Element ? event.currentTarget : null;
      const triggerRect = triggerEl?.getBoundingClientRect() ?? null;
      scheduleClose(exit, triggerRect);
    },
    [scheduleClose],
  );

  const handlePopoverMouseEnter = useCallback((): void => {
    isOverPopoverRef.current = true;
    cancelClose();
  }, [cancelClose]);

  const handlePopoverMouseLeave = useCallback(
    (event?: ReactMouseEvent): void => {
      isOverPopoverRef.current = false;
      const exit = event ? { x: event.clientX, y: event.clientY } : null;
      // No separate triggerRect on this path: `popoverElRef` already supplies
      // the popover rect, and `currentTarget` here is the same element.
      // The hull around { popoverRect, exit-point box } gives the cursor a
      // SAFE_AREA_PADDING_PX buffer past the popover edge — enough to
      // overshoot toward a header button without dismissing.
      scheduleClose(exit, null);
    },
    [scheduleClose],
  );

  const notifyPinnedToggle = useCallback(
    (open: boolean): void => {
      clearTimers();
      pendingHoverPillIdRef.current = null;
      if (!open) lastClosedAtRef.current = Date.now();
    },
    [clearTimers],
  );

  return {
    handlePillMouseEnter,
    handlePillMouseLeave,
    handlePopoverMouseEnter,
    handlePopoverMouseLeave,
    notifyPinnedToggle,
  };
};
