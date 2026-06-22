import { SIBLING_TOP_ZONE } from "~/components/panels/constants.ts";
import type { DropTarget } from "~/components/panels/SidebarDropZone";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";

export type ToggleAction =
  | { type: "close-zone"; zone: ZoneId }
  | { type: "switch-panel"; zone: ZoneId; panelId: PanelId }
  | { type: "open-zone"; zone: ZoneId };

/** Determines the toggle action for a panel click or keyboard shortcut. */
export const computeToggleAction = (inputs: {
  panelId: PanelId;
  zoneAssignments: Record<PanelId, ZoneId>;
  activePanelPerZone: Partial<Record<ZoneId, PanelId>>;
  zoneVisibility: Partial<Record<ZoneId, boolean>>;
}): ToggleAction => {
  const zone = inputs.zoneAssignments[inputs.panelId];
  const activePanel = inputs.activePanelPerZone[zone];
  const isZoneVisible = inputs.zoneVisibility[zone] ?? false;

  if (activePanel === inputs.panelId && isZoneVisible) {
    return { type: "close-zone", zone };
  }

  if (activePanel !== inputs.panelId) {
    return { type: "switch-panel", zone, panelId: inputs.panelId };
  }

  return { type: "open-zone", zone };
};

/** Returns true if moving a panel to a bottom zone would leave its sibling top zone empty.
 *  `panelsByZone` must reflect *enabled* panels only — disabled panels don't render
 *  and so don't satisfy the "non-empty top" invariant. */
export const isZoneMoveDisabled = (inputs: {
  panelId: PanelId;
  targetZone: ZoneId;
  panelsByZone: Partial<Record<ZoneId, ReadonlyArray<PanelId>>>;
}): boolean => {
  const siblingTop = SIBLING_TOP_ZONE[inputs.targetZone];
  if (!siblingTop) return false;
  const panels = inputs.panelsByZone[siblingTop] ?? [];
  return !panels.some((pid) => pid !== inputs.panelId);
};

/** Returns true when a sidebar zone has visible content (icons or an incoming drop target).
 *  During a drag, we still count the dragged icon so the divider stays until the drop completes. */
export const hasZoneContent = (inputs: {
  panelIds: ReadonlyArray<PanelId>;
  zoneId: ZoneId;
  dropTarget: DropTarget | undefined;
}): boolean => {
  const isReceiving = inputs.dropTarget?.zoneId === inputs.zoneId;
  return inputs.panelIds.length > 0 || isReceiving;
};
