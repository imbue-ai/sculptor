import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useLayoutEffect, useRef } from "react";

import {
  activePanelPerZoneAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import {
  BOTTOM_ZONE,
  CENTER_SECTION_ZONE,
  LEFT_SECTION_ZONE,
  useActivatePanel,
  useAddPanelToSection,
} from "~/components/panels/sectionHooks.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";
import { diffPanelStateAtomFamily } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { agentPanelId } from "~/pages/workspace/panels/dynamicPanels.tsx";
import { parseTerminalPanelId, terminalPanelId } from "~/pages/workspace/panels/terminals.ts";

/**
 * Bootstraps the dynamic panels that can't live in the static default layout
 * because their ids are runtime values (REQ-DEFAULT-1):
 *   - The active (URL) agent is placed into the Center section. If it's already
 *     open in some section, it is activated there instead of duplicated
 *     (single-instance, REQ-AGENT-5).
 *   - On first visit to a workspace, its terminal is placed into the Bottom
 *     section, left collapsed.
 */
export const useWorkspaceLayoutBootstrap = ({
  workspaceId,
  agentId,
}: {
  workspaceId: string;
  agentId: string | undefined;
}): void => {
  const store = useStore();
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const activatePanel = useActivatePanel();
  const movePanel = useAddPanelToSection();

  // Files opened from chat (chips, @-mentions, the command palette) write to the
  // default diff scope (the workspaceId) — the Changes panel's scope. Reveal the
  // Changes panel when a new file lands there so the diff is actually visible.
  const defaultDiffState = useAtomValue(diffPanelStateAtomFamily(workspaceId));
  const lastDiffPathRef = useRef<string | null>(null);
  useEffect(() => {
    const path = defaultDiffState.activeTabPath;
    if (!path || path === lastDiffPathRef.current) {
      lastDiffPathRef.current = path;
      return;
    }
    lastDiffPathRef.current = path;
    const changesZone = zoneAssignments["changes"];
    if (changesZone) activatePanel("changes", changesZone);
    else movePanel("changes", LEFT_SECTION_ZONE);
  }, [defaultDiffState.activeTabPath, zoneAssignments, activatePanel, movePanel]);

  // Place / focus the active agent.
  //
  // A LAYOUT effect that reads assignments from the store at effect time:
  // during a workspace switch this runs in the same pre-paint flush as
  // usePerWorkspacePanelLayout's restore (which is registered earlier in
  // WorkspacePageContent, so its layout effect has already loaded the new
  // workspace's layout into the atoms). The render-closure `zoneAssignments`
  // would still hold the PREVIOUS workspace's values here, concluding the
  // agent is unplaced and re-placing it — reordering tabs on every switch.
  useLayoutEffect(() => {
    if (!agentId) return;
    const panelId = agentPanelId(agentId);
    const currentZone = store.get(zoneAssignmentsAtom)[panelId];

    if (currentZone) {
      // Already open somewhere — make it the active tab there and reveal it.
      setActivePanelPerZone((prev) => (prev[currentZone] === panelId ? prev : { ...prev, [currentZone]: panelId }));
      setZoneVisibility((prev) => (prev[currentZone] ? prev : { ...prev, [currentZone]: true }));
      return;
    }

    placePanel({
      panelId,
      zone: CENTER_SECTION_ZONE,
      setZoneAssignments,
      setZoneOrder,
      setActivePanelPerZone,
      setActive: true,
    });
    setZoneVisibility((prev) => (prev[CENTER_SECTION_ZONE] ? prev : { ...prev, [CENTER_SECTION_ZONE]: true }));
  }, [agentId, zoneAssignments, store, setZoneAssignments, setZoneOrder, setActivePanelPerZone, setZoneVisibility]);

  // Seed the Bottom section with this workspace's terminal on first visit.
  // Pre-paint + store-read for the same reasons as the agent effect above.
  useLayoutEffect(() => {
    const hasTerminal = Object.keys(store.get(zoneAssignmentsAtom)).some(
      (id) => parseTerminalPanelId(id)?.workspaceId === workspaceId,
    );
    if (hasTerminal) return;

    placePanel({
      panelId: terminalPanelId(workspaceId, 0),
      zone: BOTTOM_ZONE,
      setZoneAssignments,
      setZoneOrder,
      setActivePanelPerZone,
      // Bottom starts collapsed (REQ-DEFAULT-1) — don't activate/reveal it.
      setActive: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);
};

const placePanel = ({
  panelId,
  zone,
  setZoneAssignments,
  setZoneOrder,
  setActivePanelPerZone,
  setActive,
}: {
  panelId: PanelId;
  zone: ZoneId;
  setZoneAssignments: (update: (prev: Record<PanelId, ZoneId>) => Record<PanelId, ZoneId>) => void;
  setZoneOrder: (
    update: (prev: Partial<Record<ZoneId, Array<PanelId>>>) => Partial<Record<ZoneId, Array<PanelId>>>,
  ) => void;
  setActivePanelPerZone: (update: (prev: Partial<Record<ZoneId, PanelId>>) => Partial<Record<ZoneId, PanelId>>) => void;
  setActive: boolean;
}): void => {
  setZoneAssignments((prev) => ({ ...prev, [panelId]: zone }));
  setZoneOrder((prev) => ({
    ...prev,
    [zone]: [...(prev[zone] ?? []).filter((id) => id !== panelId), panelId],
  }));
  setActivePanelPerZone((prev) => {
    if (setActive) return { ...prev, [zone]: panelId };
    return prev[zone] ? prev : { ...prev, [zone]: panelId };
  });
};
