import type { DragEndEvent, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, DragOverlay, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import {
  expandedPanelIdAtom,
  isBottomVisibleAtom,
  isLeftSideVisibleAtom,
  isRightSideVisibleAtom,
  isZoneVisibleAtom,
  zoneAssignmentsAtom,
  zoneSizesAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import {
  CENTER_PANEL_MIN_WIDTH_PX,
  DEFAULT_BOTTOM_PANEL_HEIGHT_PX,
  DEFAULT_INNER_BOTTOM_HEIGHT_PX,
  DEFAULT_SIDE_PANEL_WIDTH_PX,
  PANEL_MIN_PX,
  SIDE_PANEL_MIN_WIDTH_PX,
} from "~/components/panels/constants.ts";
import {
  usePanelActions,
  usePanelById,
  usePanelKeyboardShortcuts,
  usePanelsByZone,
} from "~/components/panels/hooks.ts";
import { LeftSidebar } from "~/components/panels/LeftSidebar";
import { ResizeHandle } from "~/components/panels/ResizeHandle";
import { RightSidebar } from "~/components/panels/RightSidebar";
import type { DropTarget } from "~/components/panels/SidebarDropZone";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { ZONE_IDS } from "~/components/panels/types.ts";
import { isZoneMoveDisabled } from "~/components/panels/utils.ts";
import { VerticalSplit } from "~/components/panels/VerticalSplit";
import { ZoneContent } from "~/components/panels/ZoneContent";

import styles from "./DockingLayout.module.scss";

/** Find the insertion index for a drop target based on pointer Y position. */
const computeDropIndex = (zoneId: ZoneId, pointerY: number): number => {
  const zoneEl = document.querySelector(`[data-droppable-id="${zoneId}"]`);
  if (!zoneEl) return 0;

  const iconEls = zoneEl.querySelectorAll("[data-panel-icon]");
  if (iconEls.length === 0) return 0;

  for (let i = 0; i < iconEls.length; i++) {
    const rect = iconEls[i].getBoundingClientRect();
    const centerY = rect.top + rect.height / 2;
    if (pointerY < centerY) return i;
  }
  return iconEls.length;
};

type DragOperation = {
  activeDragId: PanelId | null;
  dropTarget: DropTarget | undefined;
};

type DockingLayoutProps = {
  centerContent?: ReactNode;
};

export const DockingLayout = ({ centerContent }: DockingLayoutProps): ReactElement => {
  const isLeftVisibleBase = useAtomValue(isLeftSideVisibleAtom);
  const isRightVisibleBase = useAtomValue(isRightSideVisibleAtom);
  const isBottomVisibleBase = useAtomValue(isBottomVisibleAtom);
  const isTopLeftVisibleBase = useAtomValue(isZoneVisibleAtom("top-left"));
  const isBottomLeftVisibleBase = useAtomValue(isZoneVisibleAtom("bottom-left"));
  const isTopRightVisibleBase = useAtomValue(isZoneVisibleAtom("top-right"));
  const isBottomRightVisibleBase = useAtomValue(isZoneVisibleAtom("bottom-right"));
  const zoneSizes = useAtomValue(zoneSizesAtom);
  const setZoneSizes = useSetAtom(zoneSizesAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const panelsByZone = usePanelsByZone();
  const [expandedPanelId, setExpandedPanelId] = useAtom(expandedPanelIdAtom);

  // In expand mode, only the zone containing the expanded panel is visible.
  // All other zones (including sidebars and bottom) are hidden.
  const expandedZone = expandedPanelId ? (zoneAssignments[expandedPanelId] as ZoneId | undefined) : undefined;
  const isExpanded = expandedPanelId != null;

  const isTopLeftVisible = isExpanded ? expandedZone === "top-left" : isTopLeftVisibleBase;
  const isBottomLeftVisible = isExpanded ? expandedZone === "bottom-left" : isBottomLeftVisibleBase;
  const isTopRightVisible = isExpanded ? expandedZone === "top-right" : isTopRightVisibleBase;
  const isBottomRightVisible = isExpanded ? expandedZone === "bottom-right" : isBottomRightVisibleBase;
  const isLeftVisible = isExpanded ? expandedZone === "top-left" || expandedZone === "bottom-left" : isLeftVisibleBase;
  const isRightVisible = isExpanded
    ? expandedZone === "top-right" || expandedZone === "bottom-right"
    : isRightVisibleBase;
  const isBottomVisible = isExpanded ? false : isBottomVisibleBase;

  const { movePanel } = usePanelActions();

  const [dragOp, setDragOp] = useState<DragOperation>({ activeDragId: null, dropTarget: undefined });
  // dropTargetRef is the source of truth for the current drop target during
  // drag-move; dragOp.dropTarget drives the UI.  The ref avoids a setState on
  // every pointer-move while still giving handleDragEnd synchronous access.
  const dropTargetRef = useRef<DropTarget | undefined>(undefined);

  usePanelKeyboardShortcuts();

  // Escape key exits expand mode (only when no dialog is open)
  useEffect((): (() => void) | void => {
    if (!isExpanded) return;
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key !== "Escape") return;
      // Don't exit expand mode if a Radix dialog is open
      if (document.querySelector("[data-radix-dialog-overlay]")) return;
      e.stopPropagation();
      setExpandedPanelId(null);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isExpanded, setExpandedPanelId]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const clearDropTarget = (): void => {
    if (dropTargetRef.current !== undefined) {
      dropTargetRef.current = undefined;
      setDragOp((prev) => ({ ...prev, dropTarget: undefined }));
    }
  };

  const handleDragStart = (event: DragStartEvent): void => {
    setDragOp({ activeDragId: event.active.id as PanelId, dropTarget: undefined });
    dropTargetRef.current = undefined;
  };

  const handleDragMove = (event: DragMoveEvent): void => {
    if (!event.over) {
      clearDropTarget();
      return;
    }

    const overId = event.over.id as string;
    if (!ZONE_IDS.includes(overId as ZoneId)) {
      clearDropTarget();
      return;
    }

    const zoneId = overId as ZoneId;
    const draggedPanelId = event.active.id as PanelId;

    // Reject drops onto invalid zones (e.g. bottom-left when top-left would be empty)
    if (isZoneMoveDisabled({ panelId: draggedPanelId, targetZone: zoneId, panelsByZone })) {
      clearDropTarget();
      return;
    }

    const pointerY = event.activatorEvent instanceof PointerEvent ? event.activatorEvent.clientY + event.delta.y : 0;
    const index = computeDropIndex(zoneId, pointerY);

    const prev = dropTargetRef.current;
    if (prev?.zoneId !== zoneId || prev?.index !== index) {
      const next = { zoneId, index };
      dropTargetRef.current = next;
      setDragOp((current) => ({ ...current, dropTarget: next }));
    }
  };

  const handleDragEnd = (event: DragEndEvent): void => {
    const currentDropTarget = dropTargetRef.current;
    setDragOp({ activeDragId: null, dropTarget: undefined });
    dropTargetRef.current = undefined;

    const { active } = event;
    if (!currentDropTarget) return;

    const panelId = active.id as PanelId;
    const targetZone = currentDropTarget.zoneId;
    const insertIndex = currentDropTarget.index;

    if (isZoneMoveDisabled({ panelId, targetZone, panelsByZone })) return;

    movePanel(panelId, targetZone, insertIndex);
  };

  const handleDragCancel = (): void => {
    setDragOp({ activeDragId: null, dropTarget: undefined });
    dropTargetRef.current = undefined;
  };

  const draggedPanel = usePanelById(dragOp.activeDragId);

  // Track the PanelGroup's size so we can (a) detect when the window can't
  // fit both sides alongside the center at their minimum widths, and
  // (b) seed sensible percentage-derived defaults on first launch.
  const panelGroupRef = useRef<HTMLDivElement>(null);
  const [panelGroupSize, setPanelGroupSize] = useState({ width: 0, height: 0 });
  const { width: panelGroupWidth, height: panelGroupHeight } = panelGroupSize;

  useLayoutEffect(() => {
    const el = panelGroupRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 || rect.height > 0) {
      setPanelGroupSize({ width: rect.width, height: rect.height });
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setPanelGroupSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(el);
    return (): void => observer.disconnect();
  }, []);

  // Freeze the first non-zero measurement so percentage-derived defaults are
  // stable even if the user later resizes the window. We do NOT write these
  // defaults to zoneSizesAtom — that caused downstream re-renders that
  // destabilised other tests (e.g. clipboard/toast flows). The atom only
  // holds values the user has explicitly dragged to.
  //
  // The freeze is performed by adjusting state during render (React's
  // "storing information from previous renders" pattern) instead of in an
  // effect: once a non-zero measurement arrives we set state immediately,
  // so the frozen value is used on the same render pass with no extra cycle.
  const [initialGroupSize, setInitialGroupSize] = useState<{ width: number; height: number } | null>(null);
  if (initialGroupSize === null && panelGroupWidth > 0 && panelGroupHeight > 0) {
    setInitialGroupSize({ width: panelGroupWidth, height: panelGroupHeight });
  }

  // ── Zone sizes (pixels) ──────────────────────────────────────────────
  // Every persisted zone size is a pixel value. The layout keeps side panels
  // at their stored widths and collapses them (right first, then left) when
  // the window is too narrow to fit them alongside the center panel's
  // minimum — rather than squishing them below a usable size.
  const defaultSideWidthPx = initialGroupSize ? Math.round(initialGroupSize.width * 0.2) : DEFAULT_SIDE_PANEL_WIDTH_PX;
  const defaultBottomHeightPx = initialGroupSize
    ? Math.round(initialGroupSize.height * 0.3)
    : DEFAULT_BOTTOM_PANEL_HEIGHT_PX;
  const topLeftPx = zoneSizes["top-left"] ?? defaultSideWidthPx;
  const topRightPx = zoneSizes["top-right"] ?? defaultSideWidthPx;
  const bottomPx = zoneSizes["bottom"] ?? defaultBottomHeightPx;
  const bottomLeftPx = zoneSizes["bottom-left"] ?? DEFAULT_INNER_BOTTOM_HEIGHT_PX;
  const bottomRightPx = zoneSizes["bottom-right"] ?? DEFAULT_INNER_BOTTOM_HEIGHT_PX;

  // When the window can't fit the minimum layout, hide zones — right side
  // first, then left. This is a one-way change (not restored when the
  // window grows back); the user reopens via the sidebar icons.
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  useEffect(() => {
    if (panelGroupWidth <= 0) return;
    if (isExpanded) return;
    const leftMin = isLeftVisible ? SIDE_PANEL_MIN_WIDTH_PX : 0;
    const rightMin = isRightVisible ? SIDE_PANEL_MIN_WIDTH_PX : 0;
    if (leftMin + CENTER_PANEL_MIN_WIDTH_PX + rightMin <= panelGroupWidth) return;
    if (isRightVisible) {
      setZoneVisibility((v) => ({ ...v, "top-right": false, "bottom-right": false }));
      return;
    }

    if (isLeftVisible) {
      setZoneVisibility((v) => ({ ...v, "top-left": false, "bottom-left": false }));
    }
  }, [panelGroupWidth, isLeftVisible, isRightVisible, isExpanded, setZoneVisibility]);

  // Refs keep the latest values accessible from within the resize-handle
  // callbacks without re-creating them on every pixel of drag. Written in an
  // effect (not during render) so the values are read only after commit.
  const sizesRef = useRef(zoneSizes);
  const defaultSideWidthRef = useRef(defaultSideWidthPx);
  const defaultBottomHeightRef = useRef(defaultBottomHeightPx);
  useEffect(() => {
    sizesRef.current = zoneSizes;
    defaultSideWidthRef.current = defaultSideWidthPx;
    defaultBottomHeightRef.current = defaultBottomHeightPx;
  });

  const readSize = useCallback((key: ZoneId, fallback: number): number => sizesRef.current[key] ?? fallback, []);

  const writeSize = useCallback(
    (key: ZoneId, nextPx: number, minPx: number): void => {
      const clamped = Math.max(minPx, Math.round(nextPx));
      setZoneSizes((prev) => (prev[key] === clamped ? prev : { ...prev, [key]: clamped }));
    },
    [setZoneSizes],
  );

  const getTopLeft = useCallback(() => readSize("top-left", defaultSideWidthRef.current), [readSize]);
  const setTopLeft = useCallback((px: number) => writeSize("top-left", px, SIDE_PANEL_MIN_WIDTH_PX), [writeSize]);

  const getTopRight = useCallback(() => readSize("top-right", defaultSideWidthRef.current), [readSize]);
  const setTopRight = useCallback((px: number) => writeSize("top-right", px, SIDE_PANEL_MIN_WIDTH_PX), [writeSize]);

  const getBottom = useCallback(() => readSize("bottom", defaultBottomHeightRef.current), [readSize]);
  const setBottom = useCallback((px: number) => writeSize("bottom", px, PANEL_MIN_PX), [writeSize]);

  const getBottomLeft = useCallback(() => readSize("bottom-left", DEFAULT_INNER_BOTTOM_HEIGHT_PX), [readSize]);
  const setBottomLeft = useCallback((px: number) => writeSize("bottom-left", px, PANEL_MIN_PX), [writeSize]);

  const getBottomRight = useCallback(() => readSize("bottom-right", DEFAULT_INNER_BOTTOM_HEIGHT_PX), [readSize]);
  const setBottomRight = useCallback((px: number) => writeSize("bottom-right", px, PANEL_MIN_PX), [writeSize]);

  return (
    <DndContext
      sensors={sensors}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      <div className={styles.container}>
        {!isExpanded && <LeftSidebar dropTarget={dragOp.dropTarget} activeDragId={dragOp.activeDragId} />}

        <div ref={panelGroupRef} className={styles.panelGroup}>
          <div className={styles.outerVertical}>
            <div className={styles.topRow}>
              {isLeftVisible && (
                <>
                  <div className={styles.sidePanel} style={{ width: topLeftPx, minWidth: SIDE_PANEL_MIN_WIDTH_PX }}>
                    <VerticalSplit
                      topZoneId="top-left"
                      bottomZoneId="bottom-left"
                      isTopVisible={isTopLeftVisible}
                      isBottomVisible={isBottomLeftVisible}
                      bottomPx={bottomLeftPx}
                      getBottomSize={getBottomLeft}
                      onBottomResize={setBottomLeft}
                      handleAriaLabel="Resize bottom-left zone"
                    />
                  </div>
                  <ResizeHandle axis="x" getSize={getTopLeft} onResize={setTopLeft} ariaLabel="Resize left panel" />
                </>
              )}

              <div className={styles.centerPanel}>
                <div className={styles.centerWrapper}>
                  <div className={styles.centerInner}>
                    {centerContent ?? <div className={styles.centerContent}>Center Content</div>}
                  </div>
                </div>
              </div>

              {isRightVisible && (
                <>
                  <ResizeHandle
                    axis="x"
                    getSize={getTopRight}
                    onResize={setTopRight}
                    direction={-1}
                    ariaLabel="Resize right panel"
                  />
                  <div
                    className={styles.sidePanel}
                    style={{ width: topRightPx, minWidth: SIDE_PANEL_MIN_WIDTH_PX }}
                    data-testid={ElementIds.PANEL_RIGHT_AREA}
                  >
                    <VerticalSplit
                      topZoneId="top-right"
                      bottomZoneId="bottom-right"
                      isTopVisible={isTopRightVisible}
                      isBottomVisible={isBottomRightVisible}
                      bottomPx={bottomRightPx}
                      getBottomSize={getBottomRight}
                      onBottomResize={setBottomRight}
                      handleAriaLabel="Resize bottom-right zone"
                      topTestId={ElementIds.PANEL_TOP_RIGHT}
                      bottomTestId={ElementIds.PANEL_BOTTOM_RIGHT}
                      handleTestId={ElementIds.PANEL_RIGHT_RESIZE_HANDLE}
                    />
                  </div>
                </>
              )}
            </div>

            {isBottomVisible && (
              <>
                <ResizeHandle
                  axis="y"
                  getSize={getBottom}
                  onResize={setBottom}
                  direction={-1}
                  ariaLabel="Resize bottom panel"
                />
                <div className={styles.bottomPanel} style={{ height: bottomPx }}>
                  <ZoneContent zoneId="bottom" />
                </div>
              </>
            )}
          </div>
        </div>

        {!isExpanded && <RightSidebar dropTarget={dragOp.dropTarget} activeDragId={dragOp.activeDragId} />}
      </div>

      <DragOverlay dropAnimation={null}>
        {draggedPanel && (
          <div className={styles.dragOverlayIcon}>
            <draggedPanel.icon size={18} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
};
