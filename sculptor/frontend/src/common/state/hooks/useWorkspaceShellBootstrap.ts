// Workspace shell bootstrap — the seamless workspace-switch sequence (Task 6.1 default
// seeding; Task 6.2 first-visit terminal seed + entry ring pulse + prefetch seam).
//
// Wires the new section shell for the active workspace + agent. On entry it runs, in a
// single pre-paint (layout-effect) flush so the first committed frame already shows the
// full layout (SWITCH-01):
//   1. the scope flip to this workspace, seeding the full SEC-01..04 default arrangement
//      on the workspace's FIRST visit (and seeding the bottom terminal so SEC-03 is real);
//   2. placement of the active agent's panel into the center section.
// A separate passive effect pulses the active-section ring on entry (SEC-11). The panel
// registry is kept in sync with this workspace's agents/terminals by
// useWorkspaceDynamicPanels. A restored snapshot is never re-seeded (SWITCH-04 preserves
// what the user was looking at).

import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useLayoutEffect, useMemo } from "react";

import { ensureAgentPanelsPlacedAtom } from "~/common/state/agentPanelPlacement.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useMarkRead } from "~/common/state/hooks/useMarkRead";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import { seedFirstVisitTerminal } from "~/components/sections/addPanelCore.ts";
import { buildDefaultWorkspaceLayout } from "~/components/sections/persistence/defaultLayout.ts";
import { makeAgentPanelId, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { openPanelAtom, setActivePanelAtom } from "~/components/sections/sectionActions.ts";
import {
  isEmptyLayout,
  switchActiveWorkspaceAtom,
  workspaceLayoutAtom,
  workspaceLayoutFamily,
} from "~/components/sections/sectionAtoms.ts";
import { activeSectionRingNonceAtom } from "~/components/sections/transientAtoms.ts";
import { useAddPanelActions } from "~/components/sections/useAddPanelActions.ts";
import { useArtifactSync } from "~/pages/workspace/hooks/useArtifactSync";

import { useWorkspaceDynamicPanels } from "./useWorkspaceDynamicPanels.ts";

export const useWorkspaceShellBootstrap = (inputs: { workspaceId: string; taskId: string }): void => {
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

  // This workspace's agent task ids, recomputed only when the set of ids changes,
  // so the auto-open effect below fires on an agent appearing/disappearing rather
  // than on every per-task field tick.
  const workspaceAgentIds = useMemo(() => {
    return (tasks ?? []).filter((task) => task.workspaceId === workspaceId).map((task) => task.id);
  }, [tasks, workspaceId]);

  // Per-viewed-agent data effects that the old workspace page owned: sync the
  // viewed agent's artifacts and mark it read while it is shown in the center.
  useArtifactSync(workspaceId, taskId);
  useMarkRead(workspaceId, taskId);

  // Switch the layout scope to this workspace, seeding the SEC-01..04 default on the
  // workspace's first visit (switchActiveWorkspaceAtom only seeds when the snapshot is
  // still empty — a restored snapshot is never clobbered). On first visit the bottom
  // terminal is seeded too, so its placement in the default references a real terminal.
  // useLayoutEffect so the proxy points at the right (seeded) snapshot before the grid
  // reads it on first paint (SWITCH-01).
  useLayoutEffect(() => {
    if (isEmptyLayout(store.get(workspaceLayoutFamily(workspaceId)))) {
      const terminalIndex = seedFirstVisitTerminal(store, workspaceId);
      const defaultLayout = buildDefaultWorkspaceLayout({
        agentPanelId: makeAgentPanelId(taskId),
        terminalPanelId: makeTerminalPanelId(workspaceId, terminalIndex),
      });
      switchActiveWorkspace({ workspaceId, defaultLayout });
    } else {
      switchActiveWorkspace({ workspaceId });
    }
  }, [workspaceId, taskId, store, switchActiveWorkspace]);

  // Place the active agent in the center. Read placement imperatively (via the
  // store) so this runs once per agent id rather than on every layout change.
  useLayoutEffect(() => {
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

  // Pulse the active-section ring on workspace entry (SEC-11). A PASSIVE effect (not a
  // layout effect) so it bumps the nonce AFTER useActiveSectionRing's mount guard has
  // run — a layout-effect bump would land before that guard and be swallowed as the
  // no-flash initial mount. Bumping the nonce directly (rather than via jumpToSectionAtom)
  // fires the ring on whatever sub-section the scope switch left active, so re-entry
  // preserves the persisted active sub-section (SWITCH-04) without a redundant write.
  useEffect(() => {
    bumpRingNonce((nonce) => nonce + 1);
  }, [workspaceId, bumpRingNonce]);
};
