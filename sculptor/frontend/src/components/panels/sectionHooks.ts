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

import type { Atom } from "jotai";
import { atom, useAtomValue, useSetAtom, useStore } from "jotai";
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
import type { SplitAxis } from "~/components/panels/sectionLayoutAtoms.ts";
import { DEFAULT_SPLIT_RATIO, sectionSplitAtom } from "~/components/panels/sectionLayoutAtoms.ts";
import type { PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { isSplitZone, toPrimaryZone, toSplitZone, ZONE_IDS } from "~/components/panels/types.ts";

// The single zone backing each section. In the uniform-panels layout the
// Center is a normal section too (REQ-PANEL-1).
export const LEFT_SECTION_ZONE: ZoneId = "top-left";
export const CENTER_SECTION_ZONE: ZoneId = "center";
export const RIGHT_SECTION_ZONE: ZoneId = "top-right";
export const BOTTOM_ZONE: ZoneId = "bottom";

// Every section can host any panel now — the terminal is no longer Bottom-only
// (REQ-TERM-1) and agents/terminals are added via the "+" like any other panel.
export const SECTION_ZONES: ReadonlyArray<ZoneId> = [
  LEFT_SECTION_ZONE,
  CENTER_SECTION_ZONE,
  RIGHT_SECTION_ZONE,
  BOTTOM_ZONE,
];

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
 * Split a section into two sub-sections, moving the given panel into the new
 * (secondary) sub-section so the two appear side-by-side / stacked. A section
 * can be split at most once; callers gate on `useCanSplitSection`. The primary
 * sub-section keeps the section's remaining panels.
 */
export const useSplitSection = (zone: ZoneId): ((panelId: PanelId, axis: SplitAxis) => void) => {
  const panelIds = useAtomValue(panelsInZoneAtom(zone));
  const setSectionSplit = useSetAtom(sectionSplitAtom);
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);

  return useCallback(
    (panelId, axis) => {
      const splitZone = toSplitZone(zone);

      setSectionSplit((prev) => ({ ...prev, [zone]: { axis, ratio: DEFAULT_SPLIT_RATIO } }));

      // Move the panel into the split sub-section.
      setZoneAssignments((prev) => ({ ...prev, [panelId]: splitZone }));
      setZoneOrder((prev) => ({
        ...prev,
        [zone]: (prev[zone] ?? []).filter((id) => id !== panelId),
        [splitZone]: [...(prev[splitZone] ?? []).filter((id) => id !== panelId), panelId],
      }));
      setActivePanelPerZone((prev) => {
        const next = { ...prev, [splitZone]: panelId };
        if (prev[zone] === panelId) {
          const remaining = panelIds.filter((id) => id !== panelId);
          if (remaining.length > 0) {
            next[zone] = remaining[0];
          } else {
            delete next[zone];
          }
        }
        return next;
      });
      // Both halves stay visible — the primary must not collapse even if the
      // moved panel was its only tab (it then shows just its "+").
      setZoneVisibility((prev) => ({ ...prev, [zone]: true, [splitZone]: true }));
    },
    [zone, panelIds, setSectionSplit, setZoneAssignments, setZoneOrder, setActivePanelPerZone, setZoneVisibility],
  );
};

/** Whether a section can be split right now: a primary section zone (not itself
 *  a split half) that is not already split. Per-zone boolean atoms so a split
 *  ratio changing elsewhere (per pointer move during a resize) doesn't notify. */
const canSplitSectionAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<boolean>((get) => SECTION_ZONES.includes(zoneId) && get(sectionSplitAtom)[zoneId] === undefined),
  ]),
);

export const canSplitSectionAtom = (zone: ZoneId): Atom<boolean> => {
  return canSplitSectionAtomMap.get(zone)!;
};

export const useCanSplitSection = (zone: ZoneId): boolean => {
  return useAtomValue(canSplitSectionAtom(zone));
};

/**
 * Remove a panel from its section (the tab's close button). The panel becomes
 * "unplaced" — available again in every section's "+" dropdown.
 *
 * Closing the LAST tab in a section now collapses/unsplits that section:
 *  - a split sub-section emptied → un-split (the space goes back to its primary);
 *  - a split primary emptied → promote the split half's panels up and un-split
 *    (the surviving half becomes the whole section);
 *  - an un-split section emptied → collapse it (hide the zone), EXCEPT the
 *    Center, which always keeps an agent (its only-agent close is already
 *    blocked upstream).
 */
export const useRemovePanelFromSection = (): ((panelId: PanelId) => void) => {
  // Layout state is read from the store at call time rather than subscribed
  // to: subscribing would re-render every caller (each section's tab strip) on
  // any layout change — including per-pointer-move split-ratio updates — and
  // would give the returned callback an unstable identity.
  const store = useStore();
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setSectionSplit = useSetAtom(sectionSplitAtom);

  return useCallback(
    (panelId) => {
      const zoneAssignments = store.get(zoneAssignmentsAtom);
      const zoneOrder = store.get(zoneOrderAtom);
      const activePanelPerZone = store.get(activePanelPerZoneAtom);
      const sectionSplit = store.get(sectionSplitAtom);

      const zone = zoneAssignments[panelId];
      if (!zone) return;

      const remaining = (zoneOrder[zone] ?? []).filter((id) => id !== panelId);

      setZoneAssignments((prev) => {
        const next = { ...prev };
        delete next[panelId];
        return next;
      });
      setZoneOrder((prev) => ({ ...prev, [zone]: (prev[zone] ?? []).filter((id) => id !== panelId) }));
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

      // Not the last tab — nothing to collapse.
      if (remaining.length > 0) return;

      // The split (secondary) half emptied → un-split; the primary reclaims the space.
      if (isSplitZone(zone)) {
        setSectionSplit((prev) => {
          const next = { ...prev };
          delete next[toPrimaryZone(zone)];
          return next;
        });
        return;
      }

      // A split primary emptied → promote the split half's panels up so the
      // surviving content becomes the whole section, then un-split.
      const splitZone = toSplitZone(zone);
      const splitPanels = (Object.entries(zoneAssignments) as ReadonlyArray<[PanelId, ZoneId]>)
        .filter(([id, z]) => z === splitZone && id !== panelId)
        .map(([id]) => id);
      if (sectionSplit[zone] !== undefined && splitPanels.length > 0) {
        setZoneAssignments((prev) => {
          const next = { ...prev };
          for (const id of splitPanels) next[id] = zone;
          return next;
        });
        setZoneOrder((prev) => ({ ...prev, [zone]: prev[splitZone] ?? splitPanels, [splitZone]: [] }));
        setActivePanelPerZone((prev) => {
          const next = { ...prev };
          next[zone] = activePanelPerZone[splitZone] ?? splitPanels[0];
          delete next[splitZone];
          return next;
        });
        setSectionSplit((prev) => {
          const next = { ...prev };
          delete next[zone];
          return next;
        });
        setZoneVisibility((prev) => ({ ...prev, [zone]: true }));
        return;
      }

      // An un-split section emptied → collapse it (the Center never collapses).
      if (sectionSplit[zone] !== undefined) {
        setSectionSplit((prev) => {
          const next = { ...prev };
          delete next[zone];
          return next;
        });
      }

      if (zone !== CENTER_SECTION_ZONE) {
        setZoneVisibility((prev) => ({ ...prev, [zone]: false }));
      }
    },
    [store, setZoneAssignments, setZoneOrder, setActivePanelPerZone, setZoneVisibility, setSectionSplit],
  );
};

/**
 * Static panels addable to a section via its "+" dropdown: every registered
 * "static" panel not already in this section (adding moves it from wherever it
 * is). Agents and terminals are NOT offered here — they are created fresh and
 * closing one ends it, so there is no "open existing" pool to re-add from.
 */
export const useAddablePanels = (zone: ZoneId): ReadonlyArray<PanelDefinition> => {
  const registry = useAtomValue(panelRegistryAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  return useMemo(
    () => registry.filter((panel) => (panel.kind ?? "static") === "static" && zoneAssignments[panel.id] !== zone),
    [registry, zoneAssignments, zone],
  );
};

/**
 * Static panels not open in ANY section. The empty-section Quick add uses this
 * (rather than `useAddablePanels`, which also offers panels open elsewhere as
 * moves): quick-adding should only ever surface panels not on screen at all.
 */
export const useUnplacedStaticPanels = (): ReadonlyArray<PanelDefinition> => {
  const registry = useAtomValue(panelRegistryAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  return useMemo(
    () => registry.filter((panel) => (panel.kind ?? "static") === "static" && zoneAssignments[panel.id] === undefined),
    [registry, zoneAssignments],
  );
};
