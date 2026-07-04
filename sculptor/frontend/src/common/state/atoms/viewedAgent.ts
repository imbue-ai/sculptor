// The "viewed agent": the agent whose panel the user is looking at — the ACTIVE
// sub-section's active agent panel, falling back to the center section's active
// agent panel when the active sub-section is showing a non-agent panel (a
// terminal, Files, …). Derived from layout state, NOT the route: switching agents
// via a panel tab bar only flips the active panel without navigating, so a
// route-derived id would lag the agent actually being viewed.
//
// null when no agent panel qualifies (home/settings, an agentless workspace, or a
// workspace layout that has not been seeded yet). The id always comes from the
// ACTIVE workspace's layout, and a stale layout entry (e.g. a just-deleted
// agent's panel) can briefly name an agent that no longer exists — so consumers
// scope/validate it against their own task lists (`task.id === viewedAgentId`),
// which also leaves every other workspace's agents unaffected.
//
// This is the single source of truth for "which agent counts as viewed";
// consumers must not re-derive it from the layout atoms themselves:
//   - useWorkspaceShellBootstrap: auto mark-read + artifact sync for the viewed
//     agent (with a route fallback while a workspace switch settles);
//   - the status-dot derivations (panel tabs via useWorkspaceDynamicPanels,
//     workspace sidebar rows via workspaceDotStatusAtomFamily): the viewed agent
//     derives as "read" instead of flashing unread while the debounced mark-read
//     lags (see getAgentDotStatus's isFocused parameter).

import { atom } from "jotai";

import { AGENT_PANEL_ID_PREFIX } from "~/components/sections/registry/dynamicPanels.tsx";
import { activePanelIdInSubSectionAtom, activeSubSectionAtom } from "~/components/sections/sectionAtoms.ts";
import type { PanelId } from "~/components/sections/sectionTypes.ts";

// The agent id encoded in an agent panel id, or undefined for any other panel.
const agentIdFromPanelId = (panelId: PanelId | undefined): string | undefined =>
  panelId !== undefined && panelId.startsWith(AGENT_PANEL_ID_PREFIX)
    ? panelId.slice(AGENT_PANEL_ID_PREFIX.length)
    : undefined;

export const viewedAgentIdAtom = atom<string | null>((get) => {
  const activeSubSection = get(activeSubSectionAtom) ?? "center";
  const activePanelId = get(activePanelIdInSubSectionAtom(activeSubSection));
  const activeCenterPanelId = get(activePanelIdInSubSectionAtom("center"));
  return agentIdFromPanelId(activePanelId) ?? agentIdFromPanelId(activeCenterPanelId) ?? null;
});
