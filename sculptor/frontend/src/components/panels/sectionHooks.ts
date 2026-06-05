// Compact-layout section model.
//
// In the compact workspace layout each side (Left / Right) holds exactly ONE
// panel section: one tab strip with one active panel. A section maps onto a
// single zone in the underlying docking atoms (`top-left` for Left, `top-right`
// for Right). The old top/bottom vertical sub-split is no longer rendered, so
// `bottom-left` / `bottom-right` go unused. The Bottom zone hosts only the
// terminal.
//
// Unlike the legacy `isZoneVisibleAtom` (which force-hides an empty zone), a
// section can sit *open and empty* — it just shows its "+" button. So these
// hooks read/write the RAW `zoneVisibilityAtom` rather than the empty-guarded
// derived atom.

import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useMemo } from "react";

import {
  activePanelPerZoneAtom,
  panelRegistryAtom,
  panelsInZoneAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import { usePanelActions } from "~/components/panels/hooks.ts";
import type { PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";

// The single zone backing each peripheral section.
export const LEFT_SECTION_ZONE: ZoneId = "top-left";
export const RIGHT_SECTION_ZONE: ZoneId = "top-right";
export const BOTTOM_ZONE: ZoneId = "bottom";

// Panels that are never addable to a Left/Right section: the terminal lives
// only in the Bottom zone (REQ-ZONE-3).
const BOTTOM_ONLY_PANEL_IDS: ReadonlySet<PanelId> = new Set(["terminal"]);

/** Raw (not empty-guarded) visibility for a section's zone. */
export const useSectionVisible = (zone: ZoneId): boolean => {
  const visibility = useAtomValue(zoneVisibilityAtom);
  return visibility[zone] ?? false;
};

/**
 * Toggle a section open/closed. Sections never auto-collapse (REQ-SECTION-3);
 * collapsing is always explicit via this toggle or the top-bar buttons. When
 * opening, ensure an active panel is selected if the section has any.
 */
export const useSectionToggle = (zone: ZoneId): { isVisible: boolean; toggle: () => void } => {
  const visibility = useAtomValue(zoneVisibilityAtom);
  const setVisibility = useSetAtom(zoneVisibilityAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const panels = useAtomValue(panelsInZoneAtom(zone));
  const isVisible = visibility[zone] ?? false;

  const toggle = useCallback((): void => {
    if (isVisible) {
      setVisibility((prev) => ({ ...prev, [zone]: false }));
      return;
    }
    setVisibility((prev) => ({ ...prev, [zone]: true }));
    setActivePanelPerZone((prev) => {
      if (prev[zone] || panels.length === 0) return prev;
      return { ...prev, [zone]: panels[0] };
    });
  }, [isVisible, zone, panels, setVisibility, setActivePanelPerZone]);

  return { isVisible, toggle };
};

/** Make a panel the active tab in its section, opening the section if needed. */
export const useActivatePanel = (): ((panelId: PanelId, zone: ZoneId) => void) => {
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setVisibility = useSetAtom(zoneVisibilityAtom);
  return useCallback(
    (panelId, zone) => {
      setActivePanelPerZone((prev) => ({ ...prev, [zone]: panelId }));
      setVisibility((prev) => ({ ...prev, [zone]: true }));
    },
    [setActivePanelPerZone, setVisibility],
  );
};

/** Add a panel to a section via its "+" dropdown (moves it from wherever it is). */
export const useAddPanelToSection = (): ((panelId: PanelId, zone: ZoneId) => void) => {
  const { movePanel } = usePanelActions();
  // movePanel already assigns the zone, marks it active, and flips visibility on.
  return useCallback((panelId, zone) => movePanel(panelId, zone), [movePanel]);
};

/**
 * Remove a panel from its section (the tab's close button). The panel becomes
 * "unplaced" — available again in every section's "+" dropdown. The section
 * stays open even if it becomes empty (REQ-SECTION-3).
 */
export const useRemovePanelFromSection = (): ((panelId: PanelId) => void) => {
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);

  return useCallback(
    (panelId) => {
      const zone = zoneAssignments[panelId];
      if (!zone) return;
      setZoneAssignments((prev) => {
        const next = { ...prev };
        delete next[panelId];
        return next;
      });
      let remaining: Array<PanelId> = [];
      setZoneOrder((prev) => {
        remaining = (prev[zone] ?? []).filter((id) => id !== panelId);
        return { ...prev, [zone]: remaining };
      });
      setActivePanelPerZone((prev) => {
        if (prev[zone] !== panelId) return prev;
        const next = { ...prev };
        if (remaining.length > 0) {
          next[zone] = remaining[0];
        } else {
          delete next[zone];
        }
        return next;
      });
    },
    [zoneAssignments, setZoneAssignments, setZoneOrder, setActivePanelPerZone],
  );
};

/**
 * Panels addable to a section via its "+" dropdown: every registered panel that
 * isn't bottom-only and isn't already in this section (REQ-SECTION-2 / REQ-PANEL-2).
 */
export const useAddablePanels = (zone: ZoneId): ReadonlyArray<PanelDefinition> => {
  const registry = useAtomValue(panelRegistryAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  return useMemo(
    () => registry.filter((panel) => !BOTTOM_ONLY_PANEL_IDS.has(panel.id) && zoneAssignments[panel.id] !== zone),
    [registry, zoneAssignments, zone],
  );
};
