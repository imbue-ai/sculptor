// Workspace shell bootstrap — the seamless workspace-switch sequence (default seeding;
// first-visit terminal seed + entry ring pulse).
//
// Wires the new section shell for the active workspace + agent. On entry it runs, in a
// single pre-paint (layout-effect) flush so the first committed frame already shows the
// full layout:
//   1. the scope flip to this workspace, seeding the full default arrangement
//      on the workspace's FIRST visit (and seeding the bottom terminal so it is real);
//   2. activation of the route's agent panel (placed into center on first sight);
//   3. the additive reconcile that gives every other agent of the workspace a tab.
// A separate passive effect pulses the active-section ring on entry. The panel
// registry is kept in sync with this workspace's agents/terminals by
// useWorkspaceDynamicPanels. A restored snapshot is never re-seeded, preserving
// what the user was looking at.

import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useLayoutEffect } from "react";

import {
  activateAgentPanelAtom,
  ensureAgentPanelsPlacedAtom,
  workspaceAgentIdsAtomFamily,
} from "~/common/state/agentPanelPlacement.ts";
import { viewedAgentIdAtom } from "~/common/state/atoms/viewedAgent.ts";
import { useMarkRead } from "~/common/state/hooks/useMarkRead";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import { seedFirstVisitTerminal } from "~/components/sections/addPanelCore.ts";
import { buildDefaultWorkspaceLayout } from "~/components/sections/persistence/defaultLayout.ts";
import type { WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { makeAgentPanelId, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { consumePendingPanelRevealAtom } from "~/components/sections/sectionActions.ts";
import { isEmptyLayout, switchActiveWorkspaceAtom, workspaceLayoutFamily } from "~/components/sections/sectionAtoms.ts";
import type { PanelId } from "~/components/sections/sectionTypes.ts";
import { activeSectionRingNonceAtom } from "~/components/sections/transientAtoms.ts";
import { useAddPanelActions } from "~/components/sections/useAddPanelActions.ts";
import { useArtifactSync } from "~/pages/workspace/hooks/useArtifactSync";

import { useWorkspaceDynamicPanels } from "./useWorkspaceDynamicPanels.ts";

// The seeded default for a workspace that has NO agents yet: the standard default
// arrangement with the center left empty (its empty state offers the add-panel
// quick actions). Built by stripping a placeholder center panel from the standard
// default so the two arrangements cannot drift structurally.
function buildAgentlessDefaultLayout(terminalPanelId: PanelId): WorkspaceLayoutState {
  const placeholderPanelId = makeAgentPanelId("placeholder");
  const layout = buildDefaultWorkspaceLayout({ agentPanelId: placeholderPanelId, terminalPanelId });
  const placement = { ...layout.placement };
  delete placement[placeholderPanelId];
  const activePanel = { ...layout.activePanel };
  delete activePanel.center;
  return { ...layout, placement, activePanel, order: { ...layout.order, center: [] } };
}

// `taskId` is the route's agent id; it is undefined for a workspace with no agents,
// which renders the shell with an empty center instead of a blank page.
export const useWorkspaceShellBootstrap = (inputs: { workspaceId: string; taskId?: string }): void => {
  const { workspaceId, taskId } = inputs;

  const store = useStore();
  const switchActiveWorkspace = useSetAtom(switchActiveWorkspaceAtom);
  const consumePendingPanelReveal = useSetAtom(consumePendingPanelRevealAtom);
  const bumpRingNonce = useSetAtom(activeSectionRingNonceAtom);
  const activateAgentPanel = useSetAtom(activateAgentPanelAtom);
  const ensureAgentPanelsPlaced = useSetAtom(ensureAgentPanelsPlacedAtom);
  const { createRecentAgent } = useAddPanelActions();

  // Keep the registry in sync with this workspace's agents.
  useWorkspaceDynamicPanels(workspaceId);

  // Back the Cmd+K "New agent" command (nav.new_agent → runtime.ui.createAgent →
  // the agent.create action) with the same create-in-center flow as the add-panel
  // "+" / the new_agent keybinding. Register it here because the bootstrap is the
  // single per-workspace mount that always has the add-panel actions in scope.
  useRegisterCommandAction("agent.create", createRecentAgent);

  // This workspace's agent task ids, through the shallow-equal slice so streaming
  // ticks (which rebuild tasksArrayAtom's array without changing the id list) neither
  // re-render this host nor re-fire the reconcile effect below.
  const workspaceAgentIds = useAtomValue(workspaceAgentIdsAtomFamily(workspaceId));

  // Per-viewed-agent data effects that the old workspace page owned: sync the
  // viewed agent's artifacts and mark it read while the user is looking at it.
  //
  // The "viewed agent" (viewedAgentIdAtom — shared with the panel-tab and
  // sidebar-row dot derivations) follows the ACTIVE SUB-SECTION's active panel,
  // not the route: an agent panel the user is watching in the right/bottom
  // section (or a split half) counts as viewed just like one in the center.
  // Switching agents via a tab bar only flips the active panel (handleActivate →
  // setActivePanel) — it does not navigate — so keying off the route would leave
  // the agent you just switched to unsynced and wrongly marked unread when it
  // receives an update.
  // The panel-derived id is only trusted when it belongs to THIS workspace: on the
  // first commit of a workspace switch the layout atoms still describe the previous
  // workspace (the scope flip lands in the layout effect below), so a panel-derived
  // id that isn't one of this workspace's agents falls back to the route's taskId
  // (which also covers the window before the layout settles) rather than pairing
  // this workspace with a foreign agent. Matches ChatInput's per-panel-agent
  // isolation.
  const panelAgentId = useAtomValue(viewedAgentIdAtom);
  const viewedAgentId = panelAgentId !== null && workspaceAgentIds.includes(panelAgentId) ? panelAgentId : taskId;
  // Both hooks take a required id; in an agentless workspace the empty id matches
  // no task, so each is a safe no-op (their task lookups miss).
  useArtifactSync(workspaceId, viewedAgentId ?? "");
  useMarkRead(workspaceId, viewedAgentId ?? "");

  // Switch the layout scope to this workspace, seeding the default on the
  // workspace's first visit (switchActiveWorkspaceAtom only seeds when the snapshot is
  // still empty — a restored snapshot is never clobbered). On first visit the bottom
  // terminal is seeded too, so its placement in the default references a real terminal.
  // useLayoutEffect so the proxy points at the right (seeded) snapshot before the grid
  // reads it on first paint.
  useLayoutEffect(() => {
    if (isEmptyLayout(store.get(workspaceLayoutFamily(workspaceId)))) {
      const terminalIndex = seedFirstVisitTerminal(store, workspaceId);
      const terminalPanelId = makeTerminalPanelId(workspaceId, terminalIndex);
      const defaultLayout =
        taskId === undefined
          ? buildAgentlessDefaultLayout(terminalPanelId)
          : buildDefaultWorkspaceLayout({ agentPanelId: makeAgentPanelId(taskId), terminalPanelId });
      switchActiveWorkspace({ workspaceId, defaultLayout });
    } else {
      switchActiveWorkspace({ workspaceId });
    }
    // A panel reveal recorded before navigating here (e.g. the workspace peek
    // popover's diff click) can only land once the layout scope points at this
    // workspace; apply it now that the scope has flipped and any seeding is done.
    consumePendingPanelReveal({ workspaceId });
  }, [workspaceId, taskId, store, switchActiveWorkspace, consumePendingPanelReveal]);

  // Activate the ROUTE's agent (placing it in center if it has never been placed).
  // Keyed strictly off the route — workspaceId/taskId — and NEVER off layout state:
  // switching tabs writes activePanel without navigating, so a layout-keyed re-run
  // would snap focus straight back to the routed agent. A layout effect, so a
  // freshly-created agent's activation commits in the same pre-paint flush as its
  // navigation. Agentless workspaces (no taskId) skip activation and keep the
  // center's empty state.
  useLayoutEffect(() => {
    if (taskId === undefined) {
      return;
    }
    activateAgentPanel(taskId);
  }, [workspaceId, taskId, activateAgentPanel]);

  // Reconcile: every agent of this workspace owns a center panel tab. The activation
  // effect above only touches the route's agent; an agent that appears WITHOUT a
  // navigation (a CI-babysitter the backend spawns, or a second agent created from
  // the add-panel "+" / Cmd+K) surfaces here. The reconcile is additive-only and
  // idempotent — it never changes the active panel (a background agent's tab appears
  // without stealing focus) and re-running it on every task tick cannot duplicate a
  // tab. Runs as a layout effect so a freshly-created agent's tab is committed in the
  // same pre-paint flush as its navigation.
  useLayoutEffect(() => {
    ensureAgentPanelsPlaced(workspaceAgentIds);
  }, [workspaceAgentIds, ensureAgentPanelsPlaced]);

  // Pulse the active-section ring on workspace entry. A PASSIVE effect (not a
  // layout effect) so it bumps the nonce AFTER useActiveSectionRing's mount guard has
  // run — a layout-effect bump would land before that guard and be swallowed as the
  // no-flash initial mount. Bumping the nonce directly (rather than via jumpToSectionAtom)
  // fires the ring on whatever sub-section the scope switch left active, so re-entry
  // preserves the persisted active sub-section without a redundant write.
  useEffect(() => {
    bumpRingNonce((nonce) => nonce + 1);
  }, [workspaceId, bumpRingNonce]);
};
