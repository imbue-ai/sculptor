import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { setActiveTabByIdAtom, setAgentForWorkspaceAtom, tabOrderAtom } from "~/common/state/atoms/workspaces.ts";
import { COMPONENT_GALLERY_TAB_ID, HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";

/**
 * Mirror the current URL into `tabsAtom`: update `activeIndex` to the matching
 * tab entry on every navigation, and (for workspace routes) update the entry's
 * `agentId` to whatever the URL shows. The setters no-op when the matching
 * tab isn't yet in `tabsAtom.order`, so we also re-run on `tabOrderAtom`
 * changes — the modal-created workspace lands in the order asynchronously via
 * WebSocket, after the URL has already changed; without the tab-order
 * dependency, `activeIndex` would stay at INVALID_ACTIVE_INDEX and the
 * rootLoader would lose the user's place on next restart (SCU-MRU regression).
 */
export const useSyncActiveTabFromRoute = (): void => {
  const { workspaceID, id: agentIDFromUrl } = useParams<{ workspaceID?: string; id?: string }>();
  const { isHomeRoute, isSettingsRoute, isComponentGalleryRoute } = useImbueLocation();
  const tabOrder = useAtomValue(tabOrderAtom);
  const setActiveTabById = useSetAtom(setActiveTabByIdAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);

  useEffect(() => {
    let targetTabId: string | null = null;
    if (workspaceID) {
      targetTabId = workspaceID;
    } else if (isHomeRoute) {
      targetTabId = HOME_TAB_ID;
    } else if (isSettingsRoute) {
      targetTabId = SETTINGS_TAB_ID;
    } else if (isComponentGalleryRoute) {
      targetTabId = COMPONENT_GALLERY_TAB_ID;
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
    isHomeRoute,
    isSettingsRoute,
    isComponentGalleryRoute,
    tabOrder,
    setActiveTabById,
    setAgentForWorkspace,
  ]);
};
