// minimal cutover bootstrap; Task 6.1/6.2 expand to full default layout + seamless switch
//
// Wires the new section shell for the active workspace + agent: switches the layout
// scope to this workspace, keeps the panel registry in sync with its agents, and
// places the active agent's panel in the center section (always expanded, so it
// renders). The full default arrangement (left Files/Changes/Commits, bottom
// terminal) is Task 6.1; this is the minimal "center agent visible" cutover.

import { useSetAtom, useStore } from "jotai";
import { useLayoutEffect } from "react";

import { useMarkRead } from "~/common/state/hooks/useMarkRead";
import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { openPanelAtom, setActivePanelAtom } from "~/components/sections/sectionActions.ts";
import { switchActiveWorkspaceAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { useArtifactSync } from "~/pages/workspace/hooks/useArtifactSync";

import { useWorkspaceDynamicPanels } from "./useWorkspaceDynamicPanels.ts";

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

  // Switch the layout scope to this workspace. useLayoutEffect so the proxy points
  // at the right snapshot before the grid reads it on first paint.
  useLayoutEffect(() => {
    switchActiveWorkspace({ workspaceId });
  }, [workspaceId, switchActiveWorkspace]);

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
