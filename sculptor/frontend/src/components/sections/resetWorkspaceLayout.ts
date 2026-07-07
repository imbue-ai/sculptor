import type { useStore } from "jotai/react";

import { ensureAgentPanelsPlacedAtom, workspaceAgentIdsAtomFamily } from "~/common/state/agentPanelPlacement.ts";
import { viewedAgentIdAtom } from "~/common/state/atoms/viewedAgent.ts";
import { seedFirstVisitTerminal } from "~/components/sections/addPanelCore.ts";
import {
  buildAgentlessDefaultLayout,
  buildDefaultWorkspaceLayout,
} from "~/components/sections/persistence/defaultLayout.ts";
import { makeAgentPanelId, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";

type AppStore = ReturnType<typeof useStore>;

// Rebuild a workspace's panel layout to the default arrangement, the same way
// first-visit seeding does (see useWorkspaceShellBootstrap) but forced over a
// non-empty layout: switchActiveWorkspaceAtom's seeding only applies the default
// while the snapshot is still empty, so a reset writes the family atom directly to
// bypass that guard.
//
// The centered/active agent is the one the user is currently viewing, falling back
// to the workspace's first agent and then to the agentless arrangement when there
// are none. Sibling agents are re-placed as center tabs afterwards so a multi-agent
// workspace matches a fresh first visit instead of collapsing to a single tab.
export function resetWorkspaceLayout(store: AppStore, workspaceId: string): void {
  const agentIds = store.get(workspaceAgentIdsAtomFamily(workspaceId));
  const viewedAgentId = store.get(viewedAgentIdAtom);
  const primaryAgentId = viewedAgentId !== null && agentIds.includes(viewedAgentId) ? viewedAgentId : agentIds[0];

  // Reuse the workspace's existing first terminal (or seed one) so the default's
  // bottom placement references a real terminal, matching the bootstrap.
  const terminalIndex = seedFirstVisitTerminal(store, workspaceId);
  const terminalPanelId = makeTerminalPanelId(workspaceId, terminalIndex);

  const layout =
    primaryAgentId === undefined
      ? buildAgentlessDefaultLayout(terminalPanelId)
      : buildDefaultWorkspaceLayout({ agentPanelId: makeAgentPanelId(primaryAgentId), terminalPanelId });

  store.set(workspaceLayoutFamily(workspaceId), layout);

  // buildDefaultWorkspaceLayout only centers the primary agent; re-add every other
  // agent's center tab so the reset reproduces first-visit seeding.
  if (agentIds.length > 0) {
    store.set(ensureAgentPanelsPlacedAtom, agentIds);
  }
}
