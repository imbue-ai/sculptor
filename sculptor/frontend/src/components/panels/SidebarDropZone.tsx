import { useDroppable } from "@dnd-kit/core";
import type { ReactElement, ReactNode } from "react";

import { SidebarIcon } from "~/components/panels/SidebarIcon";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";

import styles from "./SidebarDropZone.module.scss";

export type DropTarget = {
  zoneId: ZoneId;
  index: number;
};

type SidebarDropZoneProps = {
  zoneId: ZoneId;
  panelIds: ReadonlyArray<PanelId>;
  dropTarget: DropTarget | undefined;
  activeDragId: PanelId | null;
  /** Expand to fill available rail space while this zone has no visible icons. */
  expandWhenEmpty?: boolean;
  /**
   * Expand to fill available rail space while a drag is in progress, even if
   * the zone already has icons. Used by the sided bottom zones to keep them
   * as a large drop target when both top and bottom have content.
   */
  expandDuringDrag?: boolean;
};

export const SidebarDropZone = ({
  zoneId,
  panelIds,
  dropTarget,
  activeDragId,
  expandWhenEmpty,
  expandDuringDrag,
}: SidebarDropZoneProps): ReactElement => {
  const { setNodeRef } = useDroppable({ id: zoneId });

  const isTargetZone = dropTarget?.zoneId === zoneId;
  // Unmount the dragged icon from its source zone while it's being dragged.
  // The DragOverlay in DockingLayout shows the ghost at the pointer, and a
  // placeholder rendered below marks the exact landing position. Removing the
  // icon from the DOM also keeps computeDropIndex honest — it counts only the
  // remaining icons, so the index it returns matches what the user sees.
  const visiblePanelIds = activeDragId !== null ? panelIds.filter((id) => id !== activeDragId) : panelIds;

  // When this zone is the drop target, insert a placeholder square at the
  // insertion index so the user sees exactly where the panel will land.
  const placeholderIndex = isTargetZone ? dropTarget.index : -1;
  const items: Array<ReactNode> = [];
  for (let i = 0; i <= visiblePanelIds.length; i++) {
    if (i === placeholderIndex) {
      items.push(<div key="placeholder" className={styles.placeholder} />);
    }

    if (i < visiblePanelIds.length) {
      items.push(<SidebarIcon key={visiblePanelIds[i]} panelId={visiblePanelIds[i]} zoneId={zoneId} />);
    }
  }

  const shouldExpand = (visiblePanelIds.length === 0 && expandWhenEmpty) || (activeDragId !== null && expandDuringDrag);
  const className = [styles.dropZone, shouldExpand && styles.empty].filter(Boolean).join(" ");

  return (
    <div ref={setNodeRef} className={className} data-droppable-id={zoneId}>
      {items}
    </div>
  );
};
