import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { memo } from "react";

import { focusModeActiveAtom, panelsInZoneAtom, zenModeActiveAtom } from "~/components/panels/atoms.ts";
import type { DropTarget } from "~/components/panels/SidebarDropZone";
import { SidebarDropZone } from "~/components/panels/SidebarDropZone";
import type { PanelId } from "~/components/panels/types.ts";
import { hasZoneContent } from "~/components/panels/utils.ts";

import styles from "./Sidebar.module.scss";

type RightSidebarProps = {
  dropTarget: DropTarget | undefined;
  activeDragId: PanelId | null;
};

const RightSidebarInner = ({ dropTarget, activeDragId }: RightSidebarProps): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const topRightPanels = useAtomValue(panelsInZoneAtom("top-right"));
  const bottomRightPanels = useAtomValue(panelsInZoneAtom("bottom-right"));

  const hasTopRight = hasZoneContent({ panelIds: topRightPanels, zoneId: "top-right", dropTarget });
  const hasBottomRight = hasZoneContent({ panelIds: bottomRightPanels, zoneId: "bottom-right", dropTarget });
  const shouldShowDivider = hasTopRight && hasBottomRight;
  // The bottom drop zone is visible whenever it actually has content, or when
  // top has content to drop next to. The one case it hides is when the side is
  // (or would become, via dragging the only top panel) entirely empty — then
  // only top-right is shown so drops can only land there.
  const isDraggingOnlyTopPanel =
    activeDragId !== null && topRightPanels.length === 1 && topRightPanels[0] === activeDragId;
  const shouldShowBottomRight = bottomRightPanels.length > 0 || (topRightPanels.length > 0 && !isDraggingOnlyTopPanel);

  if (isZenModeActive || isFocusModeActive) return null;

  return (
    <div className={`${styles.sidebar} ${styles.right}`}>
      <SidebarDropZone
        zoneId="top-right"
        panelIds={topRightPanels}
        dropTarget={dropTarget}
        activeDragId={activeDragId}
        expandWhenEmpty={!hasBottomRight}
      />

      {shouldShowDivider && <div className={styles.divider} />}

      {shouldShowBottomRight && (
        <SidebarDropZone
          zoneId="bottom-right"
          panelIds={bottomRightPanels}
          dropTarget={dropTarget}
          activeDragId={activeDragId}
          expandWhenEmpty
          expandDuringDrag={!isDraggingOnlyTopPanel}
        />
      )}

      <div className={styles.spacer} />
    </div>
  );
};

export const RightSidebar = memo(RightSidebarInner);
RightSidebar.displayName = "RightSidebar";
