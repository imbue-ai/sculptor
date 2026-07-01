import { useAtomValue, useSetAtom } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useRef } from "react";

import {
  activePanelPerZoneAtom,
  panelEnabledAtom,
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
};

/**
 * Hydrates the panel registry atom with the given panels on first render.
 * Optionally applies a default layout when no persisted layout exists in localStorage.
 */
export const PanelRegistryProvider = ({
  panels,
  defaultLayout,
  children,
}: PanelRegistryProviderProps): ReactElement => {
  useHydrateAtoms([[panelRegistryAtom, panels]]);

  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const activePanelPerZone = useAtomValue(activePanelPerZoneAtom);
  const zoneVisibility = useAtomValue(zoneVisibilityAtom);
  const zoneOrder = useAtomValue(zoneOrderAtom);
  const panelEnabled = useAtomValue(panelEnabledAtom);
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setPanelRegistry = useSetAtom(panelRegistryAtom);
  const hasInitialized = useRef(false);

  // useHydrateAtoms only fires on the first render. Keep the registry in sync
  // when the panels prop changes (e.g. an experimental panel is toggled on/off).
  useEffect(() => {
    setPanelRegistry(panels);
  }, [panels, setPanelRegistry]);

  // One-time bootstrap: seed defaults for any layout piece that has no persisted
  // value. Only runs on first render; later changes are handled by the
  // reconciliation effect below so dynamic panel toggling works.
  //
  // Each piece is seeded independently rather than all-or-nothing on
  // `zoneAssignments` being empty: a plugin's panel registers asynchronously,
  // and the reconciliation effect below writes `zoneAssignments` to give that
  // panel a zone. If that write lands before this bootstrap and the seed were
  // gated on `zoneAssignments` being empty, `zoneVisibility` would never get
  // seeded — and `isZoneVisibleAtom` treats a missing entry as hidden, so every
  // docked zone (file browser, terminal, …) would collapse, leaving only the
  // center panel. Seeding per-piece keeps the visibility default independent of
  // when the plugin's zone assignment lands. A returning user has all pieces
  // persisted, so nothing here overwrites their layout.
  useEffect(() => {
    if (!defaultLayout || hasInitialized.current) return;
    hasInitialized.current = true;

    if (Object.keys(zoneAssignments).length === 0) setZoneAssignments(defaultLayout.zoneAssignments);
    if (Object.keys(activePanelPerZone).length === 0) setActivePanelPerZone(defaultLayout.activePanelPerZone);
    if (Object.keys(zoneVisibility).length === 0) setZoneVisibility(defaultLayout.zoneVisibility);
    if (Object.keys(zoneOrder).length === 0) setZoneOrder(defaultLayout.zoneOrder);
  }, [
    defaultLayout,
    zoneAssignments,
    activePanelPerZone,
    zoneVisibility,
    zoneOrder,
    setZoneAssignments,
    setActivePanelPerZone,
    setZoneVisibility,
    setZoneOrder,
  ]);

  // Reconcile the persisted layout against the currently-registered panels.
  // Runs whenever the panels prop changes (e.g. an experimental panel toggle),
  // so newly-added panels get a zone and removed panels are cleaned up.
  useEffect(() => {
    if (Object.keys(zoneAssignments).length === 0) return;

    const registeredIds = new Set(panels.map((p) => p.id));
    const missingPanels = panels.filter((p) => !(p.id in zoneAssignments));
    const stalePanelIds = Object.keys(zoneAssignments).filter((id) => !registeredIds.has(id as PanelId));

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

      // The fallback must skip disabled panels: a panel can sit in a zone's
      // order while toggled off (e.g. the Browser panel, defaultEnabled:false).
      // Picking it would render a panel the user never enabled, so fall back to
      // the first *enabled* sibling instead (matching panelsInZoneAtom).
      const isEnabled = (panelId: PanelId): boolean => {
        const def = panels.find((p) => p.id === panelId);
        if (def?.isBuiltin ?? false) return true;
        return panelEnabled[panelId] ?? def?.defaultEnabled ?? true;
      };
      setActivePanelPerZone((prev) => {
        const cleaned = { ...prev };
        for (const [zone, panelId] of Object.entries(cleaned)) {
          if (panelId && staleSet.has(panelId)) {
            const remaining = (newOrder[zone as ZoneId] ?? []).filter((id) => !staleSet.has(id) && isEnabled(id));
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
    defaultLayout,
    panels,
    zoneAssignments,
    zoneOrder,
    panelEnabled,
    setZoneAssignments,
    setActivePanelPerZone,
    setZoneOrder,
  ]);

  return <>{children}</>;
};
