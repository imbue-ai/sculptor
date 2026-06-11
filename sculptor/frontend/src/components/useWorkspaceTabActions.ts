import { useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import {
  agentIdsByWorkspaceAtom,
  clearAllTabsAtom,
  closeAllWorkspaceTabsAtom,
  closeOtherWorkspaceTabsAtom,
  closeWorkspaceTabAtom,
  effectiveOpenTabIdsAtom,
  keepOnlyTabAtom,
} from "~/common/state/atoms/workspaces.ts";

import { COMPONENT_GALLERY_TAB_ID, HOME_TAB_ID, SETTINGS_TAB_ID } from "./workspaceTabIds.ts";

/**
 * The three "close-tab" handlers used by the workspace tab bar AND the
 * Cmd+K command palette. Both surfaces must close + navigate identically;
 * keeping the logic in one hook avoids the kind of drift that previously
 * left the palette's Close action removing the tab without closing the
 * workspace contents (per review of MR !1021).
 *
 * Returns three handlers and the `navigateToNextTab` helper so callers
 * that want to close-then-navigate (e.g. delete flows) can reuse the
 * same next-tab selection rules.
 */
export const useWorkspaceTabActions = (): {
  handleClose: (tabId: string) => void;
  handleCloseOthers: (tabId: string) => void;
  handleCloseAll: () => void;
  navigateToNextTab: (closedTabId: string) => void;
} => {
  const closeTab = useSetAtom(closeWorkspaceTabAtom);
  const closeOtherTabs = useSetAtom(closeOtherWorkspaceTabsAtom);
  const closeAllTabs = useSetAtom(closeAllWorkspaceTabsAtom);
  const keepOnlyTab = useSetAtom(keepOnlyTabAtom);
  const clearAllTabs = useSetAtom(clearAllTabsAtom);
  const effectiveOpenTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const { navigateToWorkspace, navigateToAgent, navigateToHome, navigateToGlobalSettings, navigateToComponentGallery } =
    useImbueNavigate();
  const { isHomeRoute, isSettingsRoute, isComponentGalleryRoute } = useImbueLocation();
  const { workspaceID: activeWorkspaceID } = useParams<{ workspaceID?: string }>();

  const handleWorkspaceClick = useCallback(
    (workspaceId: string): void => {
      const savedAgentId = agentIdsByWorkspace.get(workspaceId);
      if (savedAgentId) {
        navigateToAgent(workspaceId, savedAgentId);
        return;
      }
      navigateToWorkspace(workspaceId);
    },
    [agentIdsByWorkspace, navigateToAgent, navigateToWorkspace],
  );

  const navigateToNextTab = useCallback(
    (closedTabId: string): void => {
      const remaining = effectiveOpenTabIds.filter((id) => id !== closedTabId);
      if (remaining.length === 0) {
        // No tabs left — land on home. The user can spin up a new
        // workspace from the topbar plus button when they're ready.
        navigateToHome();
        return;
      }
      const closedIndex = effectiveOpenTabIds.indexOf(closedTabId);
      const nextTab = remaining[Math.min(closedIndex, remaining.length - 1)];
      if (nextTab === HOME_TAB_ID) {
        navigateToHome();
      } else if (nextTab === SETTINGS_TAB_ID) {
        navigateToGlobalSettings();
      } else if (nextTab === COMPONENT_GALLERY_TAB_ID) {
        navigateToComponentGallery();
      } else {
        handleWorkspaceClick(nextTab);
      }
    },
    [effectiveOpenTabIds, handleWorkspaceClick, navigateToHome, navigateToGlobalSettings, navigateToComponentGallery],
  );

  const handleClose = useCallback(
    (tabId: string): void => {
      if (tabId === HOME_TAB_ID) {
        closeTab(HOME_TAB_ID);
        if (isHomeRoute) {
          navigateToNextTab(HOME_TAB_ID);
        }
        return;
      }

      if (tabId === SETTINGS_TAB_ID) {
        closeTab(SETTINGS_TAB_ID);
        if (isSettingsRoute) {
          navigateToNextTab(SETTINGS_TAB_ID);
        }
        return;
      }

      if (tabId === COMPONENT_GALLERY_TAB_ID) {
        closeTab(COMPONENT_GALLERY_TAB_ID);
        if (isComponentGalleryRoute) {
          navigateToNextTab(COMPONENT_GALLERY_TAB_ID);
        }
        return;
      }

      // Real workspace tab: close it and navigate away if it was active.
      closeTab(tabId);
      if (tabId === activeWorkspaceID) {
        navigateToNextTab(tabId);
      }
    },
    [activeWorkspaceID, isHomeRoute, isSettingsRoute, isComponentGalleryRoute, closeTab, navigateToNextTab],
  );

  const handleCloseOthers = useCallback(
    (tabId: string): void => {
      // Keep only the specified tab — close all other workspace tabs via
      // the backend, and remove other pseudo-tabs from the local order.
      keepOnlyTab(tabId);
      closeOtherTabs(tabId);
      if (tabId === HOME_TAB_ID) {
        if (!isHomeRoute) navigateToHome();
      } else if (tabId === SETTINGS_TAB_ID) {
        if (!isSettingsRoute) navigateToGlobalSettings();
      } else if (tabId === COMPONENT_GALLERY_TAB_ID) {
        if (!isComponentGalleryRoute) navigateToComponentGallery();
      } else if (activeWorkspaceID !== tabId) {
        handleWorkspaceClick(tabId);
      }
    },
    [
      activeWorkspaceID,
      isHomeRoute,
      isSettingsRoute,
      isComponentGalleryRoute,
      keepOnlyTab,
      closeOtherTabs,
      handleWorkspaceClick,
      navigateToHome,
      navigateToGlobalSettings,
      navigateToComponentGallery,
    ],
  );

  const handleCloseAll = useCallback((): void => {
    closeAllTabs();
    clearAllTabs();
    navigateToHome();
  }, [closeAllTabs, clearAllTabs, navigateToHome]);

  return { handleClose, handleCloseOthers, handleCloseAll, navigateToNextTab };
};
