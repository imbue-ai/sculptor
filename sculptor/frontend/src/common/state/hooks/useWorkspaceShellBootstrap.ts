// Workspace shell bootstrap — the seamless workspace-switch sequence (default seeding;
// first-visit terminal seed + entry ring pulse + prefetch seam).
//
// Wires the new section shell for the active workspace + agent. On entry it runs, in a
// single pre-paint (layout-effect) flush so the first committed frame already shows the
// full layout:
//   1. the scope flip to this workspace, seeding the full default arrangement
//      on the workspace's FIRST visit (and seeding the bottom terminal so it is real);
//   2. placement of the active agent's panel into the center section.
// A separate passive effect pulses the active-section ring on entry. The panel
// registry is kept in sync with this workspace's agents/terminals by
// useWorkspaceDynamicPanels. A restored snapshot is never re-seeded, preserving
// what the user was looking at.

import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useLayoutEffect, useMemo } from "react";

import { ensureAgentPanelsPlacedAtom } from "~/common/state/agentPanelPlacement.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useMarkRead } from "~/common/state/hooks/useMarkRead";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import { seedFirstVisitTerminal } from "~/components/sections/addPanelCore.ts";
import { buildDefaultWorkspaceLayout } from "~/components/sections/persistence/defaultLayout.ts";
import type { WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import {
  AGENT_PANEL_ID_PREFIX,
  makeAgentPanelId,
  makeTerminalPanelId,
} from "~/components/sections/registry/dynamicPanels.tsx";
import { openPanelAtom, setActivePanelAtom } from "~/components/sections/sectionActions.ts";
import {
  activePanelIdInSubSectionAtom,
  activeSubSectionAtom,
  isEmptyLayout,
  switchActiveWorkspaceAtom,
  workspaceLayoutAtom,
  workspaceLayoutFamily,
} from "~/components/sections/sectionAtoms.ts";
import type { PanelId } from "~/components/sections/sectionTypes.ts";
import { activeSectionRingNonceAtom } from "~/components/sections/transientAtoms.ts";
import { useAddPanelActions } from "~/components/sections/useAddPanelActions.ts";
import { useArtifactSync } from "~/pages/workspace/hooks/useArtifactSync";

import { useWorkspaceDynamicPanels } from "./useWorkspaceDynamicPanels.ts";

// The agent id encoded in an agent panel id, or undefined for any other panel.
const agentIdFromPanelId = (panelId: PanelId | undefined): string | undefined =>
  panelId !== undefined && panelId.startsWith(AGENT_PANEL_ID_PREFIX)
    ? panelId.slice(AGENT_PANEL_ID_PREFIX.length)
    : undefined;

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
  const openPanel = useSetAtom(openPanelAtom);
  const setActivePanel = useSetAtom(setActivePanelAtom);
  const bumpRingNonce = useSetAtom(activeSectionRingNonceAtom);
  const ensureAgentPanelsPlaced = useSetAtom(ensureAgentPanelsPlacedAtom);
  const tasks = useAtomValue(tasksArrayAtom);
  const { createRecentAgent } = useAddPanelActions();

  // Keep the registry in sync with this workspace's agents.
  useWorkspaceDynamicPanels(workspaceId);

  // Back the Cmd+K "New agent" command (nav.new_agent → runtime.ui.createAgent →
  // the agent.create action) with the same create-in-center flow as the add-panel
  // "+" / the new_agent keybinding. The legacy AgentTabs registered this; that
  // surface is gone in the section shell, so register it here — the bootstrap is the
  // single per-workspace mount that always has the add-panel actions in scope.
  useRegisterCommandAction("agent.create", createRecentAgent);

  // This workspace's agent task ids. Note the useMemo re-runs on every per-task tick
  // (tasksArrayAtom returns a new array reference on any task field change), so the
  // auto-open effect below re-fires per tick — but ensureAgentPanelsPlaced no-ops when
  // nothing is missing, so it is harmless.
  const workspaceAgentIds = useMemo(() => {
    return (tasks ?? []).filter((task) => task.workspaceId === workspaceId).map((task) => task.id);
  }, [tasks, workspaceId]);

  // Per-viewed-agent data effects that the old workspace page owned: sync the
  // viewed agent's artifacts and mark it read while the user is looking at it.
  //
  // The "viewed agent" follows the ACTIVE SUB-SECTION's active panel, not the route:
  // an agent panel the user is watching in the right/bottom section (or a split
  // half) counts as viewed just like one in the center. Switching agents via a tab
  // bar only flips the active panel (handleActivate → setActivePanel) — it does not
  // navigate — so keying off the route would leave the agent you just switched to
  // unsynced and wrongly marked unread when it receives an update. When the active
  // sub-section's panel isn't an agent (a terminal, Files, …) fall back to the
  // center's agent, then to the route's taskId (e.g. before the layout settles).
  // Matches ChatInput's per-panel-agent isolation.
  const activeSubSection = useAtomValue(activeSubSectionAtom) ?? "center";
  const activePanelId = useAtomValue(activePanelIdInSubSectionAtom(activeSubSection));
  const activeCenterPanelId = useAtomValue(activePanelIdInSubSectionAtom("center"));
  const viewedAgentId = agentIdFromPanelId(activePanelId) ?? agentIdFromPanelId(activeCenterPanelId) ?? taskId;
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
  }, [workspaceId, taskId, store, switchActiveWorkspace]);

  // Place the active agent in the center. Read placement imperatively (via the
  // store) so this runs once per agent id rather than on every layout change.
  useLayoutEffect(() => {
    if (taskId === undefined) {
      return; // no agents yet — the center stays empty
    }
    const panelId = makeAgentPanelId(taskId);
    const placement = store.get(workspaceLayoutAtom).placement[panelId];
    if (placement === undefined) {
      openPanel({ panelId, in: "center" });
    } else {
      setActivePanel({ panelId, in: placement });
    }
  }, [workspaceId, taskId, store, openPanel, setActivePanel]);

  // Auto-open every agent for this workspace as a center panel tab. The active-agent
  // effect above only places the route's agent; an agent that appears WITHOUT a
  // navigation (a CI-babysitter the backend spawns, or a second agent created from
  // the add-panel "+" / Cmd+K) would otherwise be registered but never placed, so no
  // tab rendered. This reconcile is additive only — it never changes the active panel,
  // so a background agent surfaces as a new tab without stealing focus from the agent
  // the user is currently viewing. Runs as a layout effect so a freshly-created agent's
  // tab is committed in the same pre-paint flush as its navigation.
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
