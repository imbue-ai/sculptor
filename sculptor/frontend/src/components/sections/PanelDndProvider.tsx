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
// KeyboardSensor, and each tab exposes a focusable drag handle, so Playwright drives
// the real sensor pipeline (focus handle → Space → arrows → Space) — a plain
// PointerSensor cannot be driven faithfully by Playwright's synthetic mouse events.

import type { DragEndEvent, DragMoveEvent, DragOverEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useRef } from "react";

import type { PanelDragData, PanelDropData } from "./panelDnd.ts";
import { APPEND_INDEX, sectionBodyDroppableId } from "./panelDnd.ts";
import {
  panelCollisionDetection,
  panelKeyboardCoordinateGetter,
  resetKeyboardDropTarget,
  setKeyboardDropTarget,
} from "./panelDndKeyboard.ts";
import styles from "./PanelDndProvider.module.scss";
import { panelDefinitionByIdAtom } from "./registry/panelRegistry.ts";
import { jumpToSectionAtom, movePanelAtom } from "./sectionActions.ts";
import type { PanelId, SubSectionId } from "./sectionTypes.ts";
import { draggedPanelIdAtom, panelDragStateAtom } from "./transientAtoms.ts";

// A resolved drop target: where the panel would land and at which slot.
type DropTarget = { to: SubSectionId; index: number };

// The horizontal insertion slot within a sub-section's tab strip, computed from the
// pointer X. Counts only the non-dragged tabs (the live ghost is spliced into the
// rendered strip, so it must be excluded or the index is off by one). With no
// pointer (keyboard drag) the panel appends.
function computeDropIndex(subSection: SubSectionId, draggedPanelId: PanelId, pointerX: number | null): number {
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
}

// The drop target resolved from a drag event, or null when the pointer is not over a
// known drop zone (a release there is a no-op that leaves placement unchanged).
function resolveDropTarget(event: DragMoveEvent | DragOverEvent | DragEndEvent): DropTarget | null {
  const overData = event.over?.data.current as PanelDropData | undefined;
  if (overData?.kind !== "section-body") {
    return null;
  }
  const activeData = event.active.data.current as PanelDragData | undefined;
  if (activeData === undefined) {
    return null;
  }
  const pointerX = event.activatorEvent instanceof PointerEvent ? event.activatorEvent.clientX + event.delta.x : null;
  return { to: overData.subSection, index: computeDropIndex(overData.subSection, activeData.panelId, pointerX) };
}

const DragOverlayTab = ({ panelId }: { panelId: PanelId }): ReactElement | null => {
  const definition = useAtomValue(panelDefinitionByIdAtom(panelId));
  if (definition === undefined) {
    return null;
  }
  return (
    <div className={styles.overlayTab}>
      <span className={styles.overlayLabel}>{definition.displayName}</span>
    </div>
  );
};

export const PanelDndProvider = ({ children }: { children: ReactNode }): ReactElement => {
  const draggedPanelId = useAtomValue(draggedPanelIdAtom);
  const setPanelDragState = useSetAtom(panelDragStateAtom);
  const movePanel = useSetAtom(movePanelAtom);
  const jumpToSection = useSetAtom(jumpToSectionAtom);

  // The latest resolved drop target, so drag end can commit synchronously without a
  // state round-trip; null means "not over a drop zone" (release is a no-op).
  const dropTargetRef = useRef<DropTarget | null>(null);

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
      // Over a drop zone → preview the panel there; otherwise snap the ghost home.
      setPanelDragState({
        panelId: activeData.panelId,
        from: activeData.from,
        to: target?.to ?? activeData.from,
        index: target?.index ?? activeData.index,
      });
    },
    [setPanelDragState],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent): void => {
      const target = dropTargetRef.current;
      const activeData = event.active.data.current as PanelDragData | undefined;
      dropTargetRef.current = null;
      resetKeyboardDropTarget();
      setPanelDragState(null);
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
    [setPanelDragState, movePanel, jumpToSection],
  );

  const handleDragCancel = useCallback((): void => {
    dropTargetRef.current = null;
    resetKeyboardDropTarget();
    setPanelDragState(null);
  }, [setPanelDragState]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={panelCollisionDetection}
      onDragStart={handleDragStart}
      onDragOver={handleDragUpdate}
      onDragMove={handleDragUpdate}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      {children}
      <DragOverlay dropAnimation={null}>
        {draggedPanelId !== null ? <DragOverlayTab panelId={draggedPanelId} /> : null}
      </DragOverlay>
    </DndContext>
  );
};
