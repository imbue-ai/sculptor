// Agent-panel placement: keep the active workspace's agents surfaced as center
// panel tabs.
//
// The shell only ever placed the route's agent into the center section (the
// useWorkspaceShellBootstrap "active agent" effect). Agents that appear WITHOUT a
// navigation — a CI-babysitter agent the backend spawns in the background, or the
// second agent created from the add-panel "+" / Cmd+K "New agent" — were registered
// as panel definitions but never placed in a section, so no tab rendered for them.
//
// This action atom reconciles the layout so every agent task for the active
// workspace owns a center tab. It is purely ADDITIVE: it appends any missing
// agent:<taskId> panels into the center section and never removes one, changes the
// active panel, or moves the active sub-section — so surfacing a background agent as
// a new tab does not steal focus from the agent the user is currently viewing
// (the route's agent stays active via the bootstrap's own active-agent effect).
// Deleting an agent removes its panel through the agent close/delete flow, so this
// atom only needs to handle appearances.

import { atom } from "jotai";

import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SubSectionId } from "~/components/sections/sectionTypes.ts";

// New agent panels land in the center section's primary sub-section, mirroring the
// manual create path (addPanelCore → AGENT_TARGET_SUB_SECTION) and PANEL-06.
const AGENT_CENTER_SUB_SECTION: SubSectionId = "center";

// Ensure each of the given agent task ids has its panel placed (open) in the center
// section. Writes once with the full reconciled snapshot, and no-ops when nothing is
// missing so it never spins the layout's persist/notify cycle on every task tick.
export const ensureAgentPanelsPlacedAtom = atom(null, (get, set, agentTaskIds: ReadonlyArray<string>) => {
  const layout = get(workspaceLayoutAtom);

  const missing: Array<PanelId> = [];
  for (const taskId of agentTaskIds) {
    const panelId = makeAgentPanelId(taskId);
    if (layout.placement[panelId] === undefined) {
      missing.push(panelId);
    }
  }

  if (missing.length === 0) {
    return;
  }

  const placement = { ...layout.placement };
  for (const panelId of missing) {
    placement[panelId] = AGENT_CENTER_SUB_SECTION;
  }
  const order = {
    ...layout.order,
    [AGENT_CENTER_SUB_SECTION]: [...(layout.order[AGENT_CENTER_SUB_SECTION] ?? []), ...missing],
  };
  set(workspaceLayoutAtom, { ...layout, placement, order });
});
