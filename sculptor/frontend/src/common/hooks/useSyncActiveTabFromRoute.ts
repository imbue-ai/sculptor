import { useSetAtom } from "jotai";
import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { newWorkspaceTabId, setActiveTabByIdAtom, setAgentForWorkspaceAtom } from "~/common/state/atoms/workspaces.ts";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";

/**
 * Mirror the current URL into `tabsAtom`: update `activeIndex` to the matching
 * tab entry on every navigation, and (for workspace routes) update the entry's
 * `agentId` to whatever the URL shows. The setters no-op when the matching
 * tab isn't yet in `tabsAtom.order`, so the brief window between navigation
 * and tab-add is harmless — the next render picks up the new tab.
 */
export const useSyncActiveTabFromRoute = (): void => {
  const { workspaceID, id: agentIDFromUrl } = useParams<{ workspaceID?: string; id?: string }>();
  const { addWorkspaceDraftId, isHomeRoute, isSettingsRoute } = useImbueLocation();
  const setActiveTabById = useSetAtom(setActiveTabByIdAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);

  useEffect(() => {
    let targetTabId: string | null = null;
    if (workspaceID) {
      targetTabId = workspaceID;
    } else if (addWorkspaceDraftId) {
      targetTabId = newWorkspaceTabId(addWorkspaceDraftId);
    } else if (isHomeRoute) {
      targetTabId = HOME_TAB_ID;
    } else if (isSettingsRoute) {
      targetTabId = SETTINGS_TAB_ID;
    }

    if (targetTabId !== null) {
      setActiveTabById(targetTabId);
    }

    if (workspaceID) {
      setAgentForWorkspace({ wsId: workspaceID, agentId: agentIDFromUrl ?? null });
    }
  }, [
    workspaceID,
    agentIDFromUrl,
    addWorkspaceDraftId,
    isHomeRoute,
    isSettingsRoute,
    setActiveTabById,
    setAgentForWorkspace,
  ]);
};
