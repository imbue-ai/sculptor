import { useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";

import type { RecentWorkspaceResponse } from "../../../api";
import { useImbueNavigate } from "../../NavigateUtils.ts";
import { agentIdsByWorkspaceAtom, openWorkspaceTabAtom } from "../atoms/workspaces.ts";

type WorkspaceNavigationResult = {
  handleWorkspaceClick: (workspace: RecentWorkspaceResponse) => void;
  handleOpenInNewTab: (workspace: RecentWorkspaceResponse) => void;
};

/**
 * Shared workspace click handler used by pages that display a workspace list.
 * Opens the workspace tab and navigates to the most recent agent, falling back
 * to the workspace root (which resolves the server-side MRU agent).
 */
export const useWorkspaceNavigation = (): WorkspaceNavigationResult => {
  const { navigateToAgent, navigateToWorkspace } = useImbueNavigate();
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const openTab = useSetAtom(openWorkspaceTabAtom);
  const handleWorkspaceClick = useCallback(
    (workspace: RecentWorkspaceResponse): void => {
      // Ensure the workspace has an open tab (re-opens closed tabs).
      // openWorkspaceTabAtom always issues the open PATCH and records the
      // pending-open intent — even before the workspace model has loaded — so
      // reopening a closed workspace from a freshly-reloaded all-closed Home
      // succeeds instead of momentarily reverting to closed.
      openTab(workspace.objectId);

      // Use the saved agent id from tabsAtom if available for instant navigation.
      const savedAgentId = agentIdsByWorkspace.get(workspace.objectId);
      if (savedAgentId) {
        navigateToAgent(workspace.objectId, savedAgentId);
        return;
      }

      // No saved agent yet — navigate to the workspace URL and let
      // WorkspacePage's validation effect pick a fallback agent.
      navigateToWorkspace(workspace.objectId);
    },
    [openTab, agentIdsByWorkspace, navigateToAgent, navigateToWorkspace],
  );

  const handleOpenInNewTab = useCallback(
    (workspace: RecentWorkspaceResponse): void => {
      // Only open a new tab if the workspace isn't already open.
      // openWorkspaceTabAtom no-ops if the workspace is already in the tab list.
      openTab(workspace.objectId);
    },
    [openTab],
  );

  return { handleWorkspaceClick, handleOpenInNewTab };
};
