import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { focusModeActiveAtom, panelsInZoneAtom, zenModeActiveAtom } from "~/components/panels/atoms.ts";
import type { DropTarget } from "~/components/panels/SidebarDropZone";
import { SidebarDropZone } from "~/components/panels/SidebarDropZone";
import type { PanelId } from "~/components/panels/types.ts";
import { hasZoneContent } from "~/components/panels/utils.ts";

import styles from "./Sidebar.module.scss";

type LeftSidebarProps = {
  dropTarget: DropTarget | undefined;
  activeDragId: PanelId | null;
};

const LeftSidebarInner = ({ dropTarget, activeDragId }: LeftSidebarProps): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const topLeftPanels = useAtomValue(panelsInZoneAtom("top-left"));
  const bottomLeftPanels = useAtomValue(panelsInZoneAtom("bottom-left"));
  const bottomPanels = useAtomValue(panelsInZoneAtom("bottom"));

  const hasTopLeft = hasZoneContent({ panelIds: topLeftPanels, zoneId: "top-left", dropTarget });
  const hasBottomLeft = hasZoneContent({ panelIds: bottomLeftPanels, zoneId: "bottom-left", dropTarget });
  const shouldShowDivider = hasTopLeft && hasBottomLeft;
  // The bottom drop zone is visible whenever it actually has content, or when
  // top has content to drop next to. The one case it hides is when the side is
  // (or would become, via dragging the only top panel) entirely empty — then
  // only top-left is shown so drops can only land there.
  const isDraggingOnlyTopPanel =
    activeDragId !== null && topLeftPanels.length === 1 && topLeftPanels[0] === activeDragId;
  const shouldShowBottomLeft = bottomLeftPanels.length > 0 || (topLeftPanels.length > 0 && !isDraggingOnlyTopPanel);

  if (isZenModeActive || isFocusModeActive) return null;

  return (
    <div className={`${styles.sidebar} ${styles.left}`}>
      <SidebarDropZone
        zoneId="top-left"
        panelIds={topLeftPanels}
        dropTarget={dropTarget}
        activeDragId={activeDragId}
        expandWhenEmpty={!hasBottomLeft}
      />

      {shouldShowDivider && <div className={styles.divider} />}

      {shouldShowBottomLeft && (
        <SidebarDropZone
          zoneId="bottom-left"
          panelIds={bottomLeftPanels}
          dropTarget={dropTarget}
          activeDragId={activeDragId}
          expandWhenEmpty
          expandDuringDrag={!isDraggingOnlyTopPanel}
        />
      )}

      <div className={styles.spacer} />

      <SidebarDropZone zoneId="bottom" panelIds={bottomPanels} dropTarget={dropTarget} activeDragId={activeDragId} />
    </div>
  );
};

export const LeftSidebar = memo(LeftSidebarInner);
LeftSidebar.displayName = "LeftSidebar";
