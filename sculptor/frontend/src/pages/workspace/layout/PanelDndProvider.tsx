// The single app-level drag-and-drop context that wraps the whole layout — the
// drag-and-drop architecture root. Panel tabs are
// draggables; each PanelSection body and each collapsed-section toggle is a drop
// target. During a drag only the transient preview atom (panelDragStateAtom)
// updates — the real placement is mutated once, on drop, via movePanelAtom.
//
// Re-render discipline: this provider subscribes ONLY to the stable
// dragged-panel id (draggedPanelIdAtom, constant for the whole drag) so it does not
// re-render on every pointer move; the moving preview is written through useSetAtom
// (no subscription). Sections read the narrow per-sub-section preview slices
// (isDropTargetAtom / ghostPanelIdAtom / displayedPanelIdsAtom), so a pointer move
// re-renders only the sections under/around the cursor.
//
// Testability: the context runs a PointerSensor AND a
// KeyboardSensor, and each tab is itself a focusable drag activator, so Playwright
// drives the real sensor pipeline (focus tab → Space → arrows → Space) — a plain
// PointerSensor cannot be driven faithfully by Playwright's synthetic mouse events.

import type { DragEndEvent, DragMoveEvent, DragOverEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useRef } from "react";

import { jumpToSectionAtom, movePanelAtom } from "~/pages/workspace/layout/atoms/sectionActions.ts";
import {
  draggedPanelIdAtom,
  dragPointerHalvesAtom,
  NO_DRAG_POINTER_HALVES,
  panelDragStateAtom,
} from "~/pages/workspace/layout/atoms/transient.ts";
import type { PanelId, SubSectionId } from "~/pages/workspace/layout/types/section.ts";
import type { PanelDragData, PanelDropData } from "~/pages/workspace/layout/utils/panelDnd.ts";
import { APPEND_INDEX, sectionBodyDroppableId } from "~/pages/workspace/layout/utils/panelDnd.ts";
import {
  getDragPointerCoordinates,
  panelCollisionDetection,
  panelKeyboardCoordinateGetter,
  resetDragPointerCoordinates,
  resetKeyboardDropTarget,
  setKeyboardDropTarget,
} from "~/pages/workspace/layout/utils/panelDndKeyboard.ts";

import { TabPill } from "./TabPill.tsx";

// A resolved drop target: where the panel would land and at which slot.
type DropTarget = { to: SubSectionId; index: number };

// The horizontal insertion slot within a sub-section's tab strip, computed from the
// pointer X. Counts only the non-dragged tabs (the live ghost is spliced into the
// rendered strip, so it must be excluded or the index is off by one). With no
// pointer (keyboard drag) the panel appends.
const computeDropIndex = (subSection: SubSectionId, draggedPanelId: PanelId, pointerX: number | null): number => {
  if (pointerX === null) {
    return APPEND_INDEX;
  }
  const container = document.querySelector(`[data-section-tabs="${subSection}"]`);
  if (container === null) {
    return APPEND_INDEX;
  }
  const tabs = Array.from(container.querySelectorAll<HTMLElement>('[data-section-tab="true"]')).filter(
    (tab) => tab.dataset.panelId !== draggedPanelId,
  );
  for (let index = 0; index < tabs.length; index++) {
    const rect = tabs[index].getBoundingClientRect();
    if (pointerX < rect.left + rect.width / 2) {
      return index;
    }
  }
  return tabs.length;
};

// The drop target resolved from a drag event, or null when the pointer is not over a
// known drop zone (a release there is a no-op that leaves placement unchanged).
const resolveDropTarget = (event: DragMoveEvent | DragOverEvent | DragEndEvent): DropTarget | null => {
  const overData = event.over?.data.current as PanelDropData | undefined;
  if (overData?.kind !== "section-body") {
    return null;
  }
  const activeData = event.active.data.current as PanelDragData | undefined;
  if (activeData === undefined) {
    return null;
  }
  // Use the live viewport pointer (null for keyboard drags), not activatorEvent +
  // event.delta: the latter drifts by the accumulated scroll once the overflowing tab
  // strip auto-scrolls mid-drag, since event.delta folds in that scroll adjustment.
  const pointerX = getDragPointerCoordinates()?.x ?? null;
  return { to: overData.subSection, index: computeDropIndex(overData.subSection, activeData.panelId, pointerX) };
};

export const PanelDndProvider = ({ children }: { children: ReactNode }): ReactElement => {
  const draggedPanelId = useAtomValue(draggedPanelIdAtom);
  const setPanelDragState = useSetAtom(panelDragStateAtom);
  const setDragPointerHalves = useSetAtom(dragPointerHalvesAtom);
  const movePanel = useSetAtom(movePanelAtom);
  const jumpToSection = useSetAtom(jumpToSectionAtom);

  // The latest resolved drop target, so drag end can commit synchronously without a
  // state round-trip; null means "not over a drop zone" (release is a no-op).
  const dropTargetRef = useRef<DropTarget | null>(null);

  // The dragged tab's origin slot, snapshotted at drag start. During a within-section
  // reorder the tab renders at its live preview slot, so event.active.data.current.index
  // follows the preview rather than the origin — snap-home must fall back to this instead.
  const originRef = useRef<{ from: SubSectionId; index: number } | null>(null);

  // Clear all transient drag state: the resolved-target ref, the keyboard target and
  // captured pointer (module-level in panelDndKeyboard), the pointer-halves overlays,
  // and the preview atom. Shared by drag end, cancel, and unmount.
  const resetDragState = useCallback((): void => {
    dropTargetRef.current = null;
    resetKeyboardDropTarget();
    resetDragPointerCoordinates();
    setDragPointerHalves(NO_DRAG_POINTER_HALVES);
    setPanelDragState(null);
  }, [setDragPointerHalves, setPanelDragState]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    // The directional coordinate getter makes one arrow press jump to the adjacent
    // section, so the keyboard pipeline is the reliable Playwright-drivable drag path.
    useSensor(KeyboardSensor, { coordinateGetter: panelKeyboardCoordinateGetter }),
  );

  const handleDragStart = useCallback(
    (event: DragStartEvent): void => {
      const activeData = event.active.data.current as PanelDragData | undefined;
      if (activeData === undefined) {
        return;
      }
      dropTargetRef.current = { to: activeData.from, index: activeData.index };
      originRef.current = { from: activeData.from, index: activeData.index };
      // Seed the keyboard target to the source section so the initial `over` is the
      // source; each arrow updates it via the coordinate getter.
      setKeyboardDropTarget(sectionBodyDroppableId(activeData.from));
      // Seed the preview with the panel in place; drag-over refines the target.
      setPanelDragState({
        panelId: activeData.panelId,
        from: activeData.from,
        to: activeData.from,
        index: activeData.index,
      });
    },
    [setPanelDragState],
  );

  // Update on `over` change (onDragOver) AND coordinate change (onDragMove). onDragOver
  // is what makes keyboard drags reliable: a keyboard step changes `over` even when the
  // sensor's scroll-clamping suppresses the coordinate move (so onDragMove may not
  // fire); onDragMove additionally refines the pointer insertion index within a section.
  const handleDragUpdate = useCallback(
    (event: DragMoveEvent | DragOverEvent): void => {
      const activeData = event.active.data.current as PanelDragData | undefined;
      if (activeData === undefined) {
        return;
      }
      const target = resolveDropTarget(event);
      dropTargetRef.current = target;
      // Track which window halves the pointer is in — this is what reveals the
      // collapsed-section drop overlays. Keyboard drags have no pointer and
      // leave every half false (the overlays reveal via the drop-target slice).
      const pointer = getDragPointerCoordinates();
      if (pointer !== null) {
        setDragPointerHalves({
          left: pointer.x < window.innerWidth / 2,
          right: pointer.x >= window.innerWidth / 2,
          bottom: pointer.y >= window.innerHeight / 2,
        });
      }
      // Over a drop zone → preview the panel there; otherwise snap the ghost back to its
      // origin slot (originRef, not the live index, which tracks the reorder preview).
      const origin = originRef.current;
      setPanelDragState({
        panelId: activeData.panelId,
        from: activeData.from,
        to: target?.to ?? origin?.from ?? activeData.from,
        index: target?.index ?? origin?.index ?? activeData.index,
      });
    },
    [setPanelDragState, setDragPointerHalves],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent): void => {
      const target = dropTargetRef.current;
      const activeData = event.active.data.current as PanelDragData | undefined;
      resetDragState();
      if (target === null || activeData === undefined) {
        return;
      }
      movePanel({
        panelId: activeData.panelId,
        to: target.to,
        index: target.index === APPEND_INDEX ? undefined : target.index,
      });
      // Dropping into a section makes it the active section and pulses its ring.
      jumpToSection({ subSection: target.to });
    },
    [resetDragState, movePanel, jumpToSection],
  );

  // dnd-kit does not fire onDragCancel when the provider unmounts, and its
  // KeyboardSensor only auto-cancels on window resize/visibilitychange — so a keyboard
  // drag interrupted by navigation (clicking a sidebar link, a remote workspace
  // deletion) would strand the preview atom and the module-level drop target, leaving a
  // phantom ghost/highlight in every same-named sub-section. Clear on unmount too.
  useEffect(() => resetDragState, [resetDragState]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={panelCollisionDetection}
      onDragStart={handleDragStart}
      onDragOver={handleDragUpdate}
      onDragMove={handleDragUpdate}
      onDragEnd={handleDragEnd}
      onDragCancel={resetDragState}
    >
      {children}
      <DragOverlay dropAnimation={null}>
        {draggedPanelId !== null ? <TabPill panelId={draggedPanelId} variant="overlay" /> : null}
      </DragOverlay>
    </DndContext>
  );
};
