import { useAtomValue, useSetAtom } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useLayoutEffect, useRef } from "react";

import {
  activePanelPerZoneAtom,
  panelRegistryAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import type { DefaultPanelLayout, PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { ZONE_IDS } from "~/components/panels/types.ts";

type PanelRegistryProviderProps = {
  panels: ReadonlyArray<PanelDefinition>;
  defaultLayout?: DefaultPanelLayout;
  children: ReactNode;
  /**
   * When false, panels not present in the persisted layout are left *unplaced*
   * rather than auto-assigned to their `defaultZone`. The compact layout relies
   * on this: panels live in a section only once the user adds them via the "+"
   * dropdown, and closing a tab returns the panel to the unplaced pool.
   */
  autoPlaceMissing?: boolean;
  /**
   * When true, zone assignments referencing panels not in the current registry
   * are left untouched instead of being scrubbed as "stale". The uniform-panels
   * layout needs this: agent/terminal panels are per-workspace, so the global
   * zone assignments legitimately reference panels that aren't registered while
   * a different workspace is active — their placement must survive a switch.
   * (`panelsInZoneAtom` already hides unregistered ids from rendering.)
   */
  preserveUnregisteredAssignments?: boolean;
};

/**
 * Hydrates the panel registry atom with the given panels on first render.
 * Optionally applies a default layout when no persisted layout exists in localStorage.
 */
export const PanelRegistryProvider = ({
  panels,
  defaultLayout,
  children,
  autoPlaceMissing = true,
  preserveUnregisteredAssignments = false,
}: PanelRegistryProviderProps): ReactElement => {
  useHydrateAtoms([[panelRegistryAtom, panels]]);

  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const zoneOrder = useAtomValue(zoneOrderAtom);
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setPanelRegistry = useSetAtom(panelRegistryAtom);
  const hasInitialized = useRef(false);

  // useHydrateAtoms only fires on the first render. Keep the registry in sync
  // when the panels prop changes (e.g. an experimental panel is toggled on/off,
  // or a workspace switch swaps the dynamic agent/terminal panels). A layout
  // effect so the swap is committed before paint — paired with the pre-paint
  // layout restore in usePerWorkspacePanelLayout, the first painted frame
  // after a switch shows the new workspace's panels.
  useLayoutEffect(() => {
    setPanelRegistry(panels);
  }, [panels, setPanelRegistry]);

  // One-time bootstrap: apply the full defaultLayout when no persisted layout
  // exists. Only runs on first render; later changes are handled by the
  // reconciliation effect below so dynamic panel toggling works.
  useEffect(() => {
    if (!defaultLayout || hasInitialized.current) return;
    hasInitialized.current = true;

    if (Object.keys(zoneAssignments).length === 0) {
      setZoneAssignments(defaultLayout.zoneAssignments);
      setActivePanelPerZone(defaultLayout.activePanelPerZone);
      setZoneVisibility(defaultLayout.zoneVisibility);
      setZoneOrder(defaultLayout.zoneOrder);
    }
  }, [defaultLayout, zoneAssignments, setZoneAssignments, setActivePanelPerZone, setZoneVisibility, setZoneOrder]);

  // Reconcile the persisted layout against the currently-registered panels.
  // Runs whenever the panels prop changes (e.g. an experimental panel toggle),
  // so newly-added panels get a zone and removed panels are cleaned up.
  useEffect(() => {
    if (Object.keys(zoneAssignments).length === 0) return;

    const registeredIds = new Set(panels.map((p) => p.id));
    const missingPanels = autoPlaceMissing ? panels.filter((p) => !(p.id in zoneAssignments)) : [];
    const stalePanelIds = preserveUnregisteredAssignments
      ? []
      : Object.keys(zoneAssignments).filter((id) => !registeredIds.has(id as PanelId));

    // Reset panels whose stored zone is structurally invalid (not in ZONE_IDS).
    const validZones = new Set<string>(ZONE_IDS);
    const panelsWithInvalidZone = panels.filter(
      (p) => p.id in zoneAssignments && !validZones.has(zoneAssignments[p.id]),
    );

    if (missingPanels.length === 0 && stalePanelIds.length === 0 && panelsWithInvalidZone.length === 0) return;

    const newAssignments = { ...zoneAssignments };
    const newOrder = { ...zoneOrder };

    // Remove panels that are no longer registered (e.g. deleted features or
    // an experimental panel toggled off). Clean them from active-panel and
    // zone-order so zones don't render empty.
    if (stalePanelIds.length > 0) {
      const staleSet = new Set(stalePanelIds);
      for (const id of stalePanelIds) {
        delete newAssignments[id as PanelId];
      }

      for (const [zone, order] of Object.entries(newOrder)) {
        if (order) {
          newOrder[zone as ZoneId] = order.filter((id) => !staleSet.has(id));
        }
      }
      setActivePanelPerZone((prev) => {
        const cleaned = { ...prev };
        for (const [zone, panelId] of Object.entries(cleaned)) {
          if (panelId && staleSet.has(panelId)) {
            const remaining = (newOrder[zone as ZoneId] ?? []).filter((id) => !staleSet.has(id));
            cleaned[zone as ZoneId] = remaining[0] as PanelId | undefined;
          }
        }
        return cleaned;
      });
    }

    // Reset panels with structurally invalid zones to their defaultZone.
    for (const panel of panelsWithInvalidZone) {
      newAssignments[panel.id] = panel.defaultZone;
      const order = newOrder[panel.defaultZone] ?? [];
      if (!order.includes(panel.id)) {
        newOrder[panel.defaultZone] = [...order, panel.id];
      }
    }

    // Add panels that were registered after the user last saved (either a new
    // panel shipped in a release, or an experimental panel toggled on).
    for (const panel of missingPanels) {
      const zone = defaultLayout?.zoneAssignments[panel.id] ?? panel.defaultZone;
      newAssignments[panel.id] = zone;
      const order = newOrder[zone] ?? [];
      newOrder[zone] = [...order, panel.id];
    }

    setZoneAssignments(newAssignments);
    setZoneOrder(newOrder);
  }, [
    autoPlaceMissing,
    preserveUnregisteredAssignments,
    defaultLayout,
    panels,
    zoneAssignments,
    zoneOrder,
    setZoneAssignments,
    setActivePanelPerZone,
    setZoneOrder,
  ]);

  return <>{children}</>;
};
