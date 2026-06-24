// The single app-level drag-and-drop context that wraps the whole layout
// (component_hierarchy.md → "Drag-and-drop architecture"). Panel tabs are
// draggables; each PanelSection body and each collapsed-section toggle is a drop
// target. During a drag only the transient preview atom (panelDragStateAtom)
// updates — the real placement is mutated once, on drop, via movePanelAtom.
//
// Re-render discipline (SWITCH-05): this provider subscribes ONLY to the stable
// dragged-panel id (draggedPanelIdAtom, constant for the whole drag) so it does not
// re-render on every pointer move; the moving preview is written through useSetAtom
// (no subscription). Sections read the narrow per-sub-section preview slices
// (isDropTargetAtom / ghostPanelIdAtom / displayedPanelIdsAtom), so a pointer move
// re-renders only the sections under/around the cursor.
//
// Testability (harness_migration.md §3b): the context runs a PointerSensor AND a
// KeyboardSensor, and each tab exposes a focusable drag handle, so Playwright drives
// the real sensor pipeline (focus handle → Space → arrows → Space) — a plain
// PointerSensor cannot be driven faithfully by Playwright's synthetic mouse events.

import type { DragEndEvent, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useRef } from "react";

import type { PanelDragData, PanelDropData } from "./panelDnd.ts";
import { APPEND_INDEX } from "./panelDnd.ts";
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
function resolveDropTarget(event: DragMoveEvent | DragEndEvent): DropTarget | null {
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
  const Icon = definition.icon;
  return (
    <div className={styles.overlayTab}>
      <span className={styles.overlayIcon}>{definition.tabIcon ?? <Icon size={14} />}</span>
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
    useSensor(KeyboardSensor),
  );

  const handleDragStart = useCallback(
    (event: DragStartEvent): void => {
      const activeData = event.active.data.current as PanelDragData | undefined;
      if (activeData === undefined) {
        return;
      }
      dropTargetRef.current = null;
      // Seed the preview with the panel in place; drag-move refines the target.
      setPanelDragState({
        panelId: activeData.panelId,
        from: activeData.from,
        to: activeData.from,
        index: activeData.index,
      });
    },
    [setPanelDragState],
  );

  const handleDragMove = useCallback(
    (event: DragMoveEvent): void => {
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
    setPanelDragState(null);
  }, [setPanelDragState]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
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
