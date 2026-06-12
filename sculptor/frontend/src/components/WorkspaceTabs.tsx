import { ContextMenu, IconButton } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { HomeIcon, LayoutGrid, Minus, PlusIcon, Settings as SettingsGearIcon, X, XCircle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useMemo } from "react";
import { useParams } from "react-router-dom";

import { ElementIds, updateWorkspace } from "~/api";
import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { isDismissibleOverlayOpen, shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { fileBrowserTabCloseBehaviorAtom } from "~/common/state/atoms/userConfig.ts";
import {
  agentIdsByWorkspaceAtom,
  effectiveOpenTabIdsAtom,
  ensurePseudoTabAtom,
  newWorkspaceTabId,
  openNewWorkspaceTabAtom,
  openNewWorkspaceTabIdsAtom,
  parseDraftIdFromTabId,
  reorderTabsAtom,
  workspacesArrayAtom,
} from "~/common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import {
  renamingWorkspaceIdAtom,
  workspaceDeleteTargetAtom,
} from "~/components/CommandPalette/contextActions/atoms.ts";
import { type OpenInRuntime, WorkspaceContextMenuContent } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceActionRuntime } from "~/components/CommandPalette/contextActions/types.ts";
import { useGitAndOpenInRuntime } from "~/components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { buildWorkspaceActions } from "~/components/CommandPalette/contextActions/workspaceActions.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { computeWorkspaceDotStatus, EMPTY_WORKSPACE_DOT_STATUS, WorkspaceStatusDots } from "~/components/statusDot";
import { TabBar } from "~/components/tabs/TabBar";
import type { TabDefinition } from "~/components/tabs/types";
import { useWorkspaceTabActions } from "~/components/useWorkspaceTabActions.ts";
import { COMPONENT_GALLERY_TAB_ID, HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";
import {
  closeDiffTabAtom,
  diffPanelOpenAtom,
  diffPanelStateAtomFamily,
} from "~/pages/workspace/components/diffPanel/atoms.ts";
import { WorkspacePeekOverlay } from "~/pages/workspace/components/WorkspacePeekOverlay.tsx";

import styles from "./WorkspaceTabs.module.scss";

export const WorkspaceTabs = (): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const workspaces = useAtomValue(workspacesArrayAtom);
  const tasks = useAtomValue(tasksArrayAtom);
  const effectiveOpenTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);
  const reorderTabs = useSetAtom(reorderTabsAtom);
  const {
    navigateToWorkspace,
    navigateToAddWorkspace,
    navigateToAgent,
    navigateToHome,
    navigateToGlobalSettings,
    navigateToComponentGallery,
  } = useImbueNavigate();
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const keybindingsMap = useAtomValue(keybindingsMapAtom);
  const openNewWorkspaceTabIds = useAtomValue(openNewWorkspaceTabIdsAtom);
  const openNewWorkspaceTab = useSetAtom(openNewWorkspaceTabAtom);
  const { isAddWorkspaceRoute, addWorkspaceDraftId, isHomeRoute, isSettingsRoute, isComponentGalleryRoute } =
    useImbueLocation();

  const { handleClose, handleCloseOthers, handleCloseAll, navigateToNextTab } = useWorkspaceTabActions();

  const { workspaceID: activeWorkspaceID } = useParams<{ workspaceID?: string }>();
  const diffPanelState = useAtomValue(diffPanelStateAtomFamily(activeWorkspaceID ?? ""));
  const isDiffPanelOpen = useAtomValue(diffPanelOpenAtom);
  const closeDiffTab = useSetAtom(closeDiffTabAtom);
  const tabCloseBehavior = useAtomValue(fileBrowserTabCloseBehaviorAtom);

  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const [deleteTarget, setDeleteTarget] = useAtom(workspaceDeleteTargetAtom);

  // When navigating to the home route, ensure the home tab is tracked.
  useEffect(() => {
    if (isHomeRoute) {
      ensurePseudoTab(HOME_TAB_ID);
    }
  }, [isHomeRoute, ensurePseudoTab]);

  // When navigating to an add-workspace route, ensure the tab is tracked.
  useEffect(() => {
    if (addWorkspaceDraftId) {
      openNewWorkspaceTab(addWorkspaceDraftId);
    }
  }, [addWorkspaceDraftId, openNewWorkspaceTab]);

  const workspaceStatuses = useMemo(() => {
    const statusMap = new Map<string, ReturnType<typeof computeWorkspaceDotStatus>>();
    const activeTasks = tasks ?? [];

    for (const workspace of workspaces ?? []) {
      const workspaceTasks = activeTasks.filter((task) => task.workspaceId === workspace.objectId);
      statusMap.set(workspace.objectId, computeWorkspaceDotStatus(workspaceTasks));
    }

    return statusMap;
  }, [workspaces, tasks]);

  const handleRenameCommit = useCallback(
    async (workspaceId: string, newName: string): Promise<void> => {
      setRenamingWorkspaceId(null);
      try {
        await updateWorkspace({
          path: { workspace_id: workspaceId },
          body: { description: newName },
        });
      } catch (error) {
        console.error("Failed to rename workspace:", error);
      }
    },
    [setRenamingWorkspaceId],
  );

  const handleWorkspaceClick = useCallback(
    (workspaceId: string): void => {
      // Use the saved agent id from tabsAtom if available for instant navigation.
      const savedAgentId = agentIdsByWorkspace.get(workspaceId);
      if (savedAgentId) {
        navigateToAgent(workspaceId, savedAgentId);
        return;
      }

      // No saved agent yet (brand-new workspace, or this user's first session
      // after the migration). Navigate to the workspace URL and let
      // WorkspacePage's validation effect pick a fallback agent.
      navigateToWorkspace(workspaceId);
    },
    [agentIdsByWorkspace, navigateToAgent, navigateToWorkspace],
  );

  const handleWorkspacePeekNavigate = useCallback(
    (workspaceId: string, agentId?: string): void => {
      if (agentId) {
        navigateToAgent(workspaceId, agentId);
      } else {
        handleWorkspaceClick(workspaceId);
      }
    },
    [navigateToAgent, handleWorkspaceClick],
  );

  const handleNavigateAfterDelete = useCallback(
    (workspaceId: string): void => {
      navigateToNextTab(workspaceId);
    },
    [navigateToNextTab],
  );

  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    onNavigateAfterDelete: handleNavigateAfterDelete,
  });

  const handleDeleteConfirm = useCallback((): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete, setDeleteTarget]);

  // Imperative tab-cycle action — invoked both by the next/previous
  // keybindings (below) and by the Cmd+K commands (via
  // `useRegisterCommandAction`). Direction is +1 / -1.
  const cycleTab = useCallback(
    (direction: 1 | -1): void => {
      if (effectiveOpenTabIds.length === 0) return;

      const currentIndex = activeWorkspaceID
        ? effectiveOpenTabIds.indexOf(activeWorkspaceID)
        : isHomeRoute
          ? effectiveOpenTabIds.indexOf(HOME_TAB_ID)
          : isSettingsRoute
            ? effectiveOpenTabIds.indexOf(SETTINGS_TAB_ID)
            : isComponentGalleryRoute
              ? effectiveOpenTabIds.indexOf(COMPONENT_GALLERY_TAB_ID)
              : addWorkspaceDraftId
                ? effectiveOpenTabIds.indexOf(newWorkspaceTabId(addWorkspaceDraftId))
                : -1;

      const nextIndex = (currentIndex + direction + effectiveOpenTabIds.length) % effectiveOpenTabIds.length;
      const nextTabId = effectiveOpenTabIds[nextIndex];

      if (nextTabId === HOME_TAB_ID) {
        navigateToHome();
      } else if (nextTabId === SETTINGS_TAB_ID) {
        navigateToGlobalSettings();
      } else if (nextTabId === COMPONENT_GALLERY_TAB_ID) {
        navigateToComponentGallery();
      } else {
        const draftId = parseDraftIdFromTabId(nextTabId);
        if (draftId !== null) {
          navigateToAddWorkspace(draftId);
        } else {
          handleWorkspaceClick(nextTabId);
        }
      }
    },
    [
      activeWorkspaceID,
      addWorkspaceDraftId,
      effectiveOpenTabIds,
      isHomeRoute,
      isSettingsRoute,
      isComponentGalleryRoute,
      handleWorkspaceClick,
      navigateToAddWorkspace,
      navigateToHome,
      navigateToGlobalSettings,
      navigateToComponentGallery,
    ],
  );

  const goToNextTab = useCallback((): void => cycleTab(1), [cycleTab]);
  const goToPreviousTab = useCallback((): void => cycleTab(-1), [cycleTab]);

  // Close the current workspace tab. Called both from the close_workspace
  // keybinding and from the Cmd+K "Close" entry on the Workspace Actions
  // sub-page (which carries the same shortcut hint). Delegates to the
  // shared `handleClose` so keybinding, X button, right-click, and Cmd+K
  // close paths all behave identically.
  const closeCurrentTab = useCallback((): void => {
    // If the document viewer has an active diff tab, close it first
    // instead of closing the surrounding workspace.
    if (activeWorkspaceID && isDiffPanelOpen && diffPanelState.activeTabPath) {
      closeDiffTab({
        workspaceId: activeWorkspaceID,
        filePath: diffPanelState.activeTabPath,
        tabCloseBehavior,
      });
      return;
    }

    let currentTabId: string | null = null;
    if (isAddWorkspaceRoute && addWorkspaceDraftId) {
      currentTabId = newWorkspaceTabId(addWorkspaceDraftId);
    } else if (isHomeRoute) {
      currentTabId = HOME_TAB_ID;
    } else if (isSettingsRoute) {
      currentTabId = SETTINGS_TAB_ID;
    } else if (isComponentGalleryRoute) {
      currentTabId = COMPONENT_GALLERY_TAB_ID;
    } else if (activeWorkspaceID) {
      currentTabId = activeWorkspaceID;
    }

    if (currentTabId !== null) {
      handleClose(currentTabId);
    }
  }, [
    activeWorkspaceID,
    isAddWorkspaceRoute,
    addWorkspaceDraftId,
    isHomeRoute,
    isSettingsRoute,
    isComponentGalleryRoute,
    handleClose,
    diffPanelState,
    isDiffPanelOpen,
    closeDiffTab,
    tabCloseBehavior,
  ]);

  useRegisterCommandAction("workspace.nextTab", goToNextTab);
  useRegisterCommandAction("workspace.previousTab", goToPreviousTab);
  useRegisterCommandAction("workspace.closeCurrent", closeCurrentTab);

  // Next/Previous tab: cycle through open workspace tabs
  useEffect(() => {
    const handleTabCycle = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;

      const nextBinding = keybindingsMap.next_tab.binding;
      const prevBinding = keybindingsMap.previous_tab.binding;

      let direction: 1 | -1 | null = null;
      if (nextBinding != null && shouldHandleKeybinding(e, nextBinding)) {
        direction = 1;
      } else if (prevBinding != null && shouldHandleKeybinding(e, prevBinding)) {
        direction = -1;
      }

      if (direction == null) return;

      e.preventDefault();
      cycleTab(direction);
    };

    window.addEventListener("keydown", handleTabCycle);
    return (): void => window.removeEventListener("keydown", handleTabCycle);
  }, [keybindingsMap, cycleTab]);

  // Close workspace shortcut: close the current workspace tab (remove tab, no delete)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;
      const closeBinding = keybindingsMap.close_workspace.binding;
      if (closeBinding == null || !shouldHandleKeybinding(e, closeBinding)) return;
      e.preventDefault();
      // Blur the focused element first so onBlur-driven saves (e.g. the
      // settings setup-command textarea) commit before unmount.
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
      closeCurrentTab();
    };

    window.addEventListener("keydown", handleKeyDown);
    return (): void => window.removeEventListener("keydown", handleKeyDown);
  }, [keybindingsMap, closeCurrentTab]);

  // Build TabDefinition array from workspaces
  const tabs = useMemo((): Array<TabDefinition> => {
    const workspaceTabs: Array<TabDefinition> = (workspaces ?? []).map((workspace) => {
      const status = workspaceStatuses.get(workspace.objectId) ?? EMPTY_WORKSPACE_DOT_STATUS;
      const isRenaming = renamingWorkspaceId === workspace.objectId;

      return {
        id: workspace.objectId,
        label: workspace.description ?? "Untitled",
        icon: <WorkspaceStatusDots status={status} />,
        closeIcon: <Minus width={14} height={14} />,
        dataTestId: ElementIds.WORKSPACE_TAB,
        dataAttributes: { "workspace-tab": "", "has-unread": String(status.hasUnread) },
        labelContent: isRenaming ? (
          <InlineRenameInput
            value={workspace.description ?? ""}
            onCommit={(newName) => void handleRenameCommit(workspace.objectId, newName)}
            onCancel={() => setRenamingWorkspaceId(null)}
            isEditing={true}
          />
        ) : undefined,
      };
    });

    if (effectiveOpenTabIds.includes(HOME_TAB_ID) || isHomeRoute) {
      workspaceTabs.push({
        id: HOME_TAB_ID,
        label: "Home",
        icon: <HomeIcon size={14} />,
        dataTestId: ElementIds.HOME_TAB,
      });
    }

    if (effectiveOpenTabIds.includes(SETTINGS_TAB_ID) || isSettingsRoute) {
      workspaceTabs.push({
        id: SETTINGS_TAB_ID,
        label: "Settings",
        icon: <SettingsGearIcon size={14} />,
        dataTestId: ElementIds.SETTINGS_TAB,
      });
    }

    if (effectiveOpenTabIds.includes(COMPONENT_GALLERY_TAB_ID) || isComponentGalleryRoute) {
      workspaceTabs.push({
        id: COMPONENT_GALLERY_TAB_ID,
        label: "Component Gallery",
        icon: <LayoutGrid size={14} />,
        dataTestId: ElementIds.COMPONENT_GALLERY_TAB,
      });
    }

    for (const draftId of openNewWorkspaceTabIds) {
      workspaceTabs.push({
        id: newWorkspaceTabId(draftId),
        label: "New Workspace",
        icon: <PlusIcon size={14} />,
        dataTestId: ElementIds.ADD_WORKSPACE_TAB,
      });
    }

    return workspaceTabs;
  }, [
    workspaces,
    workspaceStatuses,
    renamingWorkspaceId,
    setRenamingWorkspaceId,
    effectiveOpenTabIds,
    isHomeRoute,
    isSettingsRoute,
    isComponentGalleryRoute,
    openNewWorkspaceTabIds,
    handleRenameCommit,
  ]);

  // effectiveOpenTabIds is the single source of truth for tab order — it
  // already contains new-workspace pseudo-tab IDs in their correct position.
  const openTabIds = effectiveOpenTabIds;

  const activeTabId = isHomeRoute
    ? HOME_TAB_ID
    : isSettingsRoute
      ? SETTINGS_TAB_ID
      : isComponentGalleryRoute
        ? COMPONENT_GALLERY_TAB_ID
        : addWorkspaceDraftId
          ? newWorkspaceTabId(addWorkspaceDraftId)
          : (activeWorkspaceID ?? "");

  const handleActivate = useCallback(
    (tabId: string): void => {
      const draftId = parseDraftIdFromTabId(tabId);
      if (draftId !== null) {
        navigateToAddWorkspace(draftId);
        return;
      }

      if (tabId === HOME_TAB_ID) {
        navigateToHome();
        return;
      }

      if (tabId === SETTINGS_TAB_ID) {
        navigateToGlobalSettings();
        return;
      }

      if (tabId === COMPONENT_GALLERY_TAB_ID) {
        navigateToComponentGallery();
        return;
      }
      handleWorkspaceClick(tabId);
    },
    [
      handleWorkspaceClick,
      navigateToAddWorkspace,
      navigateToHome,
      navigateToGlobalSettings,
      navigateToComponentGallery,
    ],
  );

  const handleDoubleClick = useCallback(
    (tabId: string): void => {
      if (
        parseDraftIdFromTabId(tabId) !== null ||
        tabId === HOME_TAB_ID ||
        tabId === SETTINGS_TAB_ID ||
        tabId === COMPONENT_GALLERY_TAB_ID
      )
        return;
      setRenamingWorkspaceId(tabId);
    },
    [setRenamingWorkspaceId],
  );

  const handleReorder = useCallback(
    (newOrder: Array<string>): void => {
      reorderTabs(newOrder);
    },
    [reorderTabs],
  );

  // Workspace context menu items come from the shared registry — adding
  // a row here means appending to `buildWorkspaceActions()` and it lights
  // up in Cmd+K → Workspace actions… too.
  const gitAndOpenIn = useGitAndOpenInRuntime();
  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      beginRename: (ws): void => setRenamingWorkspaceId(ws.objectId),
      closeWorkspace: (ws): void => handleClose(ws.objectId),
      closeOtherWorkspaces: (ws): void => handleCloseOthers(ws.objectId),
      closeAllWorkspaces: (): void => handleCloseAll(),
      beginDelete: (ws): void => setDeleteTarget({ id: ws.objectId, name: ws.description ?? "" }),
      canCloseOthers: (): boolean => effectiveOpenTabIds.length > 1,
      ...gitAndOpenIn,
    }),
    [
      setRenamingWorkspaceId,
      handleClose,
      handleCloseOthers,
      handleCloseAll,
      setDeleteTarget,
      effectiveOpenTabIds.length,
      gitAndOpenIn,
    ],
  );
  const workspaceActions = useMemo(() => buildWorkspaceActions(workspaceActionRuntime), [workspaceActionRuntime]);
  const openInRuntime = useMemo<OpenInRuntime>(
    () => ({
      openInApp: gitAndOpenIn.openInApp,
      canOpenInOS: gitAndOpenIn.canOpenInOS,
      isMacUi: gitAndOpenIn.isMacUi,
    }),
    [gitAndOpenIn],
  );

  const contextMenuContent = useCallback(
    (tabId: string): ReactNode => {
      if (parseDraftIdFromTabId(tabId) !== null) return undefined;

      // System tabs (Home / Settings / Component Gallery) only support
      // close operations, never rename or delete. We hand-render this
      // small variant rather than wiring three separate registries.
      if (tabId === HOME_TAB_ID || tabId === SETTINGS_TAB_ID || tabId === COMPONENT_GALLERY_TAB_ID) {
        return (
          <ContextMenu.Content size="1">
            <ContextMenu.Item data-testid={ElementIds.TAB_CONTEXT_MENU_CLOSE} onSelect={() => handleClose(tabId)}>
              <X size={14} /> Close
            </ContextMenu.Item>
            <ContextMenu.Item
              data-testid={ElementIds.TAB_CONTEXT_MENU_CLOSE_OTHERS}
              onSelect={() => handleCloseOthers(tabId)}
              disabled={effectiveOpenTabIds.length <= 1}
            >
              <XCircle size={14} /> Close others
            </ContextMenu.Item>
            <ContextMenu.Item data-testid={ElementIds.TAB_CONTEXT_MENU_CLOSE_ALL} onSelect={handleCloseAll}>
              <XCircle size={14} /> Close all
            </ContextMenu.Item>
          </ContextMenu.Content>
        );
      }

      const workspace = (workspaces ?? []).find((ws) => ws.objectId === tabId);
      if (workspace == null) return undefined;
      return (
        <WorkspaceContextMenuContent
          actions={workspaceActions}
          workspace={workspace}
          destructiveColor={dangerColor}
          openInRuntime={openInRuntime}
        />
      );
    },
    [
      workspaces,
      effectiveOpenTabIds.length,
      handleClose,
      handleCloseOthers,
      handleCloseAll,
      dangerColor,
      workspaceActions,
      openInRuntime,
    ],
  );

  return (
    <>
      <TabBar
        tabs={tabs}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
        onDoubleClick={handleDoubleClick}
        tabBarClassName={styles.tabBar}
        // Always render the X — closing the last tab navigates the user
        // to the AddWorkspace page (handled in useWorkspaceTabActions).
        alwaysCloseable={true}
        contextMenuContent={contextMenuContent}
      >
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.addButton}
          onClick={() => navigateToAddWorkspace()}
          aria-label="Add workspace"
          data-testid={ElementIds.ADD_WORKSPACE_BUTTON}
        >
          <PlusIcon size={14} />
        </IconButton>
      </TabBar>
      <WorkspacePeekOverlay onNavigate={handleWorkspacePeekNavigate} />
      <DeleteConfirmationDialog
        isOpen={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        entityType="workspace"
        entityName={deleteTarget?.name ?? ""}
        onConfirm={handleDeleteConfirm}
      />
    </>
  );
};
