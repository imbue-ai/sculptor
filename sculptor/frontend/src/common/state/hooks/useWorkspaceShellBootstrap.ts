// Workspace shell bootstrap (Task 6.1 default seeding; Task 6.2 expands the seamless
// switch + terminal seed + ring pulse).
//
// Wires the new section shell for the active workspace + agent: switches the layout
// scope to this workspace (seeding the full SEC-01..04 default arrangement on the
// workspace's first visit), keeps the panel registry in sync with its agents, and
// places the active agent's panel in the center section (always expanded, so it
// renders).

import { useSetAtom, useStore } from "jotai";
import { useLayoutEffect } from "react";

import { useMarkRead } from "~/common/state/hooks/useMarkRead";
import { buildDefaultWorkspaceLayout } from "~/components/sections/persistence/defaultLayout.ts";
import { makeAgentPanelId, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { openPanelAtom, setActivePanelAtom } from "~/components/sections/sectionActions.ts";
import { switchActiveWorkspaceAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { useArtifactSync } from "~/pages/workspace/hooks/useArtifactSync";

import { useWorkspaceDynamicPanels } from "./useWorkspaceDynamicPanels.ts";

// The first-visit seeded terminal is always index 0 (the bottom section's lone
// terminal). Task 6.2 creates the matching terminal entry; the default only records
// its placement so the section is arranged correctly the instant it is expanded.
const FIRST_VISIT_TERMINAL_INDEX = 0;

export const useWorkspaceShellBootstrap = (inputs: { workspaceId: string; taskId: string }): void => {
  const { workspaceId, taskId } = inputs;

  const store = useStore();
  const switchActiveWorkspace = useSetAtom(switchActiveWorkspaceAtom);
  const openPanel = useSetAtom(openPanelAtom);
  const setActivePanel = useSetAtom(setActivePanelAtom);

  // Keep the registry in sync with this workspace's agents.
  useWorkspaceDynamicPanels(workspaceId);

  // Per-viewed-agent data effects that the old workspace page owned: sync the
  // viewed agent's artifacts and mark it read while it is shown in the center.
  useArtifactSync(workspaceId, taskId);
  useMarkRead(workspaceId, taskId);

  // Switch the layout scope to this workspace, seeding the SEC-01..04 default on the
  // workspace's first visit (switchActiveWorkspaceAtom only seeds when the snapshot is
  // still empty — a restored snapshot is never clobbered). useLayoutEffect so the
  // proxy points at the right (seeded) snapshot before the grid reads it on first paint.
  useLayoutEffect(() => {
    const defaultLayout = buildDefaultWorkspaceLayout({
      agentPanelId: makeAgentPanelId(taskId),
      terminalPanelId: makeTerminalPanelId(workspaceId, FIRST_VISIT_TERMINAL_INDEX),
    });
    switchActiveWorkspace({ workspaceId, defaultLayout });
  }, [workspaceId, taskId, switchActiveWorkspace]);

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
};
