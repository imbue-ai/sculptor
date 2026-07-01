import { useAtomValue, useSetAtom } from "jotai";
import { useCallback } from "react";
import { useParams } from "react-router-dom";

import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import {
  agentIdsByWorkspaceAtom,
  clearAllTabsAtom,
  closeAllWorkspaceTabsAtom,
  closeNewWorkspaceTabAtom,
  closeOtherWorkspaceTabsAtom,
  closeWorkspaceTabAtom,
  effectiveOpenTabIdsAtom,
  keepOnlyTabAtom,
  parseDraftIdFromTabId,
} from "~/common/state/atoms/workspaces.ts";

import { COMPONENT_GALLERY_TAB_ID, HOME_TAB_ID, SETTINGS_TAB_ID } from "./workspaceTabIds.ts";

/**
 * The three "close-tab" handlers used by the workspace tab bar AND the
 * Cmd+K command palette. Both surfaces must close + navigate identically;
 * keeping the logic in one hook avoids drift between them.
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
  const closeNewWorkspaceTab = useSetAtom(closeNewWorkspaceTabAtom);
  const keepOnlyTab = useSetAtom(keepOnlyTabAtom);
  const clearAllTabs = useSetAtom(clearAllTabsAtom);
  const effectiveOpenTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const {
    navigateToWorkspace,
    navigateToAddWorkspace,
    navigateToAgent,
    navigateToHome,
    navigateToGlobalSettings,
    navigateToComponentGallery,
  } = useImbueNavigate();
  const { addWorkspaceDraftId, isHomeRoute, isSettingsRoute, isComponentGalleryRoute } = useImbueLocation();
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
        navigateToAddWorkspace();
        return;
      }
      // closedTabId may already be gone from effectiveOpenTabIds — e.g. an
      // optimistic delete removed the tab before this runs — making indexOf
      // return -1. Clamp to a valid range so we land on the first surviving tab
      // instead of reading remaining[-1] (undefined).
      const closedIndex = effectiveOpenTabIds.indexOf(closedTabId);
      const nextTab = remaining[Math.min(Math.max(closedIndex, 0), remaining.length - 1)];
      if (nextTab === HOME_TAB_ID) {
        navigateToHome();
      } else if (nextTab === SETTINGS_TAB_ID) {
        navigateToGlobalSettings();
      } else if (nextTab === COMPONENT_GALLERY_TAB_ID) {
        navigateToComponentGallery();
      } else {
        const draftId = parseDraftIdFromTabId(nextTab);
        if (draftId !== null) {
          navigateToAddWorkspace(draftId);
        } else {
          handleWorkspaceClick(nextTab);
        }
      }
    },
    [
      effectiveOpenTabIds,
      handleWorkspaceClick,
      navigateToAddWorkspace,
      navigateToHome,
      navigateToGlobalSettings,
      navigateToComponentGallery,
    ],
  );

  const handleClose = useCallback(
    (tabId: string): void => {
      const draftId = parseDraftIdFromTabId(tabId);
      if (draftId !== null) {
        closeNewWorkspaceTab(draftId);
        if (addWorkspaceDraftId === draftId) {
          navigateToNextTab(tabId);
        }
        return;
      }

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
    [
      activeWorkspaceID,
      addWorkspaceDraftId,
      isHomeRoute,
      isSettingsRoute,
      isComponentGalleryRoute,
      closeTab,
      closeNewWorkspaceTab,
      navigateToNextTab,
    ],
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
    navigateToAddWorkspace();
  }, [closeAllTabs, clearAllTabs, navigateToAddWorkspace]);

  return { handleClose, handleCloseOthers, handleCloseAll, navigateToNextTab };
};
