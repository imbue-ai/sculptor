import { useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";

import type { RecentWorkspaceResponse } from "../../../api";
import { useImbueLocation, useImbueNavigate } from "../../hooks/navigation.ts";
import { agentIdsByWorkspaceAtom, convertHomeTabToWorkspaceAtom, openWorkspaceTabAtom } from "../atoms/workspaces.ts";

type WorkspaceNavigationResult = {
  navigateToWorkspaceById: (workspaceId: string) => void;
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
  // The id-keyed core of the click handler, so callers that only hold a
  // workspace id (e.g. the plugin SDK's navigate verb) get the same tab-opening
  // and MRU-agent resolution without reconstructing a RecentWorkspaceResponse.
  const navigateToWorkspaceById = useCallback(
    (workspaceId: string): void => {
      // When navigating from the home page, replace the home tab with the workspace tab.
      if (isHomeRoute) {
        convertHomeTab(workspaceId);
      } else {
        // Ensure the workspace has an open tab (re-opens closed tabs)
        openTab(workspaceId);
      }

      // Use the saved agent id from tabsAtom if available for instant navigation.
      const savedAgentId = agentIdsByWorkspace.get(workspaceId);
      if (savedAgentId) {
        navigateToAgent(workspaceId, savedAgentId);
        return;
      }

      // No saved agent yet — navigate to the workspace URL and let
      // WorkspacePage's validation effect pick a fallback agent.
      navigateToWorkspace(workspaceId);
    },
    [isHomeRoute, openTab, convertHomeTab, agentIdsByWorkspace, navigateToAgent, navigateToWorkspace],
  );
  const handleWorkspaceClick = useCallback(
    (workspace: RecentWorkspaceResponse): void => {
      navigateToWorkspaceById(workspace.objectId);
    },
    [navigateToWorkspaceById],
  );

  const handleOpenInNewTab = useCallback(
    (workspace: RecentWorkspaceResponse): void => {
      // Only open a new tab if the workspace isn't already open.
      // openWorkspaceTabAtom no-ops if the workspace is already in the tab list.
      openTab(workspace.objectId);
    },
    [openTab],
  );

  return { navigateToWorkspaceById, handleWorkspaceClick, handleOpenInNewTab };
};
