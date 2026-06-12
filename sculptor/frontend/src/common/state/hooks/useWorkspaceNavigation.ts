import { useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";

import type { RecentWorkspaceResponse } from "../../../api";
import { useImbueLocation, useImbueNavigate } from "../../NavigateUtils.ts";
import { agentIdsByWorkspaceAtom, convertHomeTabToWorkspaceAtom, openWorkspaceTabAtom } from "../atoms/workspaces.ts";

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
  const { isHomeRoute } = useImbueLocation();
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const openTab = useSetAtom(openWorkspaceTabAtom);
  const convertHomeTab = useSetAtom(convertHomeTabToWorkspaceAtom);
  const handleWorkspaceClick = useCallback(
    (workspace: RecentWorkspaceResponse): void => {
      // When navigating from the home page, replace the home tab with the workspace tab.
      if (isHomeRoute) {
        convertHomeTab(workspace.objectId);
      } else {
        // Ensure the workspace has an open tab (re-opens closed tabs)
        openTab(workspace.objectId);
      }

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
    [isHomeRoute, openTab, convertHomeTab, agentIdsByWorkspace, navigateToAgent, navigateToWorkspace],
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
