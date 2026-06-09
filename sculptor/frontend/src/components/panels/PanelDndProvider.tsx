import type { CollisionDetection, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import {
  DndContext,
  DragOverlay,
  MeasuringStrategy,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useAtomValue, useSetAtom, useStore } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { useCallback } from "react";

import {
  panelDragStateAtom,
  panelRegistryAtom,
  panelsInZoneAtom,
  zoneAssignmentsAtom,
} from "~/components/panels/atoms.ts";
import { usePanelActions } from "~/components/panels/hooks.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { ZONE_IDS } from "~/components/panels/types.ts";
import tabStyles from "~/components/tabs/SortableTab.module.scss";

import styles from "./PanelDndProvider.module.scss";

// While a tab drag is active, route pointer events back to the host window so
// Electron <webview> panels (terminals, browser) don't swallow pointermove and
// freeze the drag — same mechanism ResizeHandle uses for resize drags.
const BODY_DRAG_CLASS = "sculptor-resizing";

// Section droppables are keyed by their ZoneId; tab droppables by PanelId. Panel
// ids never collide with zone ids, so set membership tells the two apart.
const ZONE_ID_SET: ReadonlySet<string> = new Set<string>(ZONE_IDS);
const isSectionId = (id: string | number): boolean => ZONE_ID_SET.has(String(id));

// The current pointer x in client coordinates, reconstructed from the original
// pointerdown event plus the accumulated drag delta (dnd-kit doesn't surface
// live pointer coordinates on drag events directly).
const pointerClientX = (event: DragMoveEvent): number | undefined => {
  const activator = event.activatorEvent;
  if (activator !== null && "clientX" in activator) {
    return (activator as PointerEvent).clientX + event.delta.x;
  }
  return undefined;
};

type PanelDndProviderProps = {
  children: ReactNode;
};

/**
 * The single app-level DndContext for the compact layout. Every PanelSection
 * registers its body as a droppable (keyed by its zone) and every tab as a
 * draggable, so a tab can be dragged from one section into another. During a
 * drag we only update `panelDragStateAtom` (a preview); the real zone atoms are
 * mutated once, on drop, via `movePanel` — which already handles cross-zone
 * moves, insertion index, and split-section collapse.
 */
export const PanelDndProvider = ({ children }: PanelDndProviderProps): ReactElement => {
  const store = useStore();
  const drag = useAtomValue(panelDragStateAtom);
  const setDrag = useSetAtom(panelDragStateAtom);
  const { movePanel } = usePanelActions();

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  // Prefer the pointer-hit tab over the section it sits inside (so we can derive
  // a precise insertion index), and never collide with the dragged tab itself.
  const collisionDetection = useCallback<CollisionDetection>((args) => {
    const pointerHits = pointerWithin(args);
    const hits = pointerHits.length > 0 ? pointerHits : rectIntersection(args);
    const usable = hits.filter((hit) => hit.id !== args.active.id);
    const tabHit = usable.find((hit) => !isSectionId(hit.id));
    return tabHit ? [tabHit] : usable;
  }, []);

  const resetDrag = useCallback((): void => {
    setDrag(null);
    document.body.classList.remove(BODY_DRAG_CLASS);
  }, [setDrag]);

  const handleDragStart = useCallback(
    (event: DragStartEvent): void => {
      const activePanelId = event.active.id as PanelId;
      const sourceZone = store.get(zoneAssignmentsAtom)[activePanelId];
      if (sourceZone === undefined) return;
      const order = store.get(panelsInZoneAtom(sourceZone));
      setDrag({
        activePanelId,
        sourceZone,
        targetZone: sourceZone,
        insertIndex: order.indexOf(activePanelId),
      });
      document.body.classList.add(BODY_DRAG_CLASS);
    },
    [store, setDrag],
  );

  // We compute the insertion index on drag *move* (not drag *over*): onDragOver
  // only fires when the hovered droppable changes, so a before/after-the-tab
  // decision based on pointer position would only update once, on entry. onDragMove
  // fires on every pointer move and still carries the current `over`.
  const handleDragMove = useCallback(
    (event: DragMoveEvent): void => {
      const { active, over } = event;
      if (over === null) return; // pointer left every droppable — keep last target
      const activePanelId = active.id as PanelId;
      const overId = over.id;
      if (overId === activePanelId) return; // hovering the dragged tab's own ghost

      const assignments = store.get(zoneAssignmentsAtom);
      const sourceZone = assignments[activePanelId];
      if (sourceZone === undefined) return;

      setDrag((prev) => {
        let targetZone: ZoneId;
        let insertIndex: number;
        if (isSectionId(overId)) {
          targetZone = overId as ZoneId;
          const base = store.get(panelsInZoneAtom(targetZone)).filter((id) => id !== activePanelId);
          // Hovering the section body. If we're already targeting this zone, keep
          // the index the tab-level branch settled on — otherwise the relocated
          // ghost sliding under the pointer (which resolves `over` to the section)
          // would flip the insertion point back to the end. Only when first
          // entering a zone via its body do we land at the end.
          insertIndex = prev !== null && prev.targetZone === targetZone ? prev.insertIndex : base.length;
        } else {
          // Over another tab → land before or after it based on pointer position.
          const overPanelId = overId as PanelId;
          targetZone = assignments[overPanelId] ?? sourceZone;
          const base = store.get(panelsInZoneAtom(targetZone)).filter((id) => id !== activePanelId);
          const overIndex = base.indexOf(overPanelId);
          if (overIndex === -1) {
            insertIndex = base.length;
          } else {
            // Use the live pointer x (activator position + drag delta) rather than
            // the active element's rect: with a DragOverlay the source tab has no
            // transform, so its rect stays put and can't tell us before/after.
            const pointerX = pointerClientX(event) ?? over.rect.left;
            const overCenter = over.rect.left + over.rect.width / 2;
            insertIndex = pointerX < overCenter ? overIndex : overIndex + 1;
          }
        }

        if (prev !== null && prev.targetZone === targetZone && prev.insertIndex === insertIndex) return prev;
        return { activePanelId, sourceZone, targetZone, insertIndex };
      });
    },
    [store, setDrag],
  );

  const handleDragEnd = useCallback((): void => {
    const current = store.get(panelDragStateAtom);
    resetDrag();
    if (current === null) return;
    movePanel(current.activePanelId, current.targetZone, current.insertIndex);
  }, [store, resetDrag, movePanel]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisionDetection}
      measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      onDragCancel={resetDrag}
    >
      {children}
      <DragOverlay dropAnimation={null}>{drag ? <DragTabPreview panelId={drag.activePanelId} /> : null}</DragOverlay>
    </DndContext>
  );
};

type DragTabPreviewProps = {
  panelId: PanelId;
};

/** The full-colour floating copy of the dragged tab shown in the DragOverlay. */
const DragTabPreview = ({ panelId }: DragTabPreviewProps): ReactElement | null => {
  const registry = useAtomValue(panelRegistryAtom);
  const def = registry.find((p) => p.id === panelId);
  if (def === undefined) return null;
  const Icon = def.icon;
  return (
    <div className={`${styles.overlayTab} ${tabStyles.tabCompact} ${tabStyles.compactActive}`}>
      <span className={tabStyles.icon}>{def.tabIcon ?? <Icon size={13} />}</span>
      <span className={tabStyles.compactLabel}>{def.displayName}</span>
    </div>
  );
};
