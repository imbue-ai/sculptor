import { IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom, useStore } from "jotai";
import { Bug, Command, Home, PanelLeftClose, Plus, Settings } from "lucide-react";
import { Tooltip as TooltipPrimitive } from "radix-ui";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import type { Workspace } from "~/api";
import { ElementIds } from "~/api";
import { DevModeIndicator } from "~/app/nav/DevModeIndicator.tsx";
import { ReportProblemPopover } from "~/app/nav/ReportProblemPopover.tsx";
import { VersionPopover } from "~/app/nav/VersionPopover.tsx";
import { useImbueLocation, useImbueNavigate } from "~/common/hooks/navigation.ts";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { type ToastContent } from "~/common/state/atoms/toasts.ts";
import { agentIdsByWorkspaceAtom, ensurePseudoTabAtom } from "~/common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { useWorkspaceTabActions } from "~/common/state/hooks/useWorkspaceTabActions.ts";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "~/common/utils/workspaceTabIds.ts";
import { AddRepoDialog } from "~/components/addRepo/AddRepoDialog.tsx";
import { useCommandPalette } from "~/components/commandPalette";
import { renamingWorkspaceIdAtom } from "~/components/commandPalette/contextActions/atoms/contextActions.ts";
import type { OpenInRuntime } from "~/components/commandPalette/contextActions/menu.tsx";
import type { WorkspaceActionRuntime } from "~/components/commandPalette/contextActions/types.ts";
import { useGitAndOpenInRuntime } from "~/components/commandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { buildWorkspaceActions } from "~/components/commandPalette/contextActions/workspaceActions.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { isWorkspaceListEmptyAtom, newWorkspaceDialogAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { Toast } from "~/components/Toast.tsx";
import { WorkspacePeekOverlay } from "~/components/workspacePeek/WorkspacePeekOverlay.tsx";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { sidebarCollapsedAtom, sidebarWidthAtom } from "~/pages/workspace/layout/atoms/sidebar.ts";
import { layoutPersistenceAdapter } from "~/pages/workspace/layout/persistence/LocalStorageLayoutAdapter.ts";
import { ResizeHandle } from "~/pages/workspace/layout/ResizeHandle.tsx";

import navItemStyles from "./NavItem.module.scss";
import { NavItem } from "./NavItem.tsx";
import { SidebarEmptyState } from "./SidebarEmptyState.tsx";
import { SidebarRepoGroup } from "./SidebarRepoGroup.tsx";
import { sidebarWorkspaceGroupsAtom } from "./sidebarWorkspaceOrder.ts";
import styles from "./WorkspaceSidebar.module.scss";

/** Smallest sidebar width the resize handle allows, in pixels. */
const MIN_SIDEBAR_WIDTH_PX = 180;

/**
 * Vertical navigation sidebar — the global chrome rail that replaces the old
 * top bar. Top links (Home / Cmd+K / New workspace), then repos
 * as collapsible groups with their workspaces, then Settings / report-a-bug /
 * version anchored to the bottom. A drag handle on the right border resizes it
 * and the collapse toggle hides it down to `CollapsedSidebarToggle`. Width and
 * collapsed state persist globally via the layout snapshot.
 */
export const WorkspaceSidebar = (): ReactElement | null => {
  // External atoms
  const isCollapsed = useAtomValue(sidebarCollapsedAtom);
  const setCollapsed = useSetAtom(sidebarCollapsedAtom);
  const width = useAtomValue(sidebarWidthAtom);
  const setWidth = useSetAtom(sidebarWidthAtom);
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);
  const projects = useAtomValue(projectsArrayAtom);
  // Grouped + sorted workspace rows, shared with keyboard workspace cycling so the
  // two can't drift (see sidebarWorkspaceOrder).
  const repoGroups = useAtomValue(sidebarWorkspaceGroupsAtom);
  const setRenamingWorkspaceId = useSetAtom(renamingWorkspaceIdAtom);
  // The workspace→last-agent map is only consulted inside the click handler, so
  // read it lazily from the store rather than subscribing: the whole sidebar
  // would otherwise re-render (and churn the click callbacks) on every agent-id
  // change, with no visual effect.
  const store = useStore();
  // In the empty first-run state the repo area shows its own
  // "Add a repo" / "No workspaces yet" affordances; outside it the sidebar is
  // unchanged.
  const isWorkspaceListEmpty = useAtomValue(isWorkspaceListEmptyAtom);

  // Internal state — the add-repo dialog opened from the empty-state
  // "Add a repo" button (and its toast).
  const [isAddRepoDialogOpen, setIsAddRepoDialogOpen] = useState<boolean>(false);
  const [addRepoToast, setAddRepoToast] = useState<ToastContent | null>(null);
  // Deleting a workspace is destructive, so it is confirmed first. The trash
  // icon and both Delete menu entries set this target to open the shared
  // confirmation dialog; confirming runs the optimistic delete below.
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);

  // External hooks
  const { navigateToWorkspace, navigateToAgent, navigateToHome, navigateToGlobalSettings } = useImbueNavigate();
  const setNewWorkspaceDialog = useSetAtom(newWorkspaceDialogAtom);
  const { toggle: toggleCommandPalette } = useCommandPalette();
  const { workspaceId: activeWorkspaceId, isHomeRoute, isSettingsRoute } = useImbueLocation();
  const { navigateToNextTab } = useWorkspaceTabActions();
  const gitAndOpenIn = useGitAndOpenInRuntime();
  // Deleting a workspace updates the sidebar optimistically and rolls back with
  // an error toast on failure. Navigate away only when the deleted
  // workspace is the active one.
  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    onNavigateAfterDelete: (workspaceId): void => {
      if (workspaceId === activeWorkspaceId) {
        navigateToNextTab(workspaceId);
      }
    },
  });

  // Functions and callbacks
  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      beginRename: (ws): void => setRenamingWorkspaceId(ws.objectId),
      beginDelete: (ws): void => setDeleteTarget(ws),
      ...gitAndOpenIn,
    }),
    [setRenamingWorkspaceId, gitAndOpenIn],
  );

  // Run the optimistic delete once the user confirms in the dialog.
  const handleDeleteConfirm = useCallback((): void => {
    if (deleteTarget === null) {
      return;
    }
    executeDelete(deleteTarget.objectId, deleteTarget.description ?? "");
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete]);
  const workspaceActions = useMemo(() => buildWorkspaceActions(workspaceActionRuntime), [workspaceActionRuntime]);
  const openInRuntime = useMemo<OpenInRuntime>(
    () => ({
      openInApp: gitAndOpenIn.openInApp,
      canOpenInOS: gitAndOpenIn.canOpenInOS,
      isMacUi: gitAndOpenIn.isMacUi,
    }),
    [gitAndOpenIn],
  );

  const handleWorkspaceClick = useCallback(
    (workspaceId: string): void => {
      const savedAgentId = store.get(agentIdsByWorkspaceAtom).get(workspaceId);
      if (savedAgentId) {
        navigateToAgent(workspaceId, savedAgentId);
        return;
      }
      navigateToWorkspace(workspaceId);
    },
    [store, navigateToAgent, navigateToWorkspace],
  );

  // Navigation-intent prefetch seam: warm the workspace's persisted layout
  // on hover. A no-op for the localStorage adapter (reads are synchronous); the seam is
  // here so the future backend adapter can fetch the snapshot before the user clicks.
  const handleWorkspaceHover = useCallback((workspaceId: string): void => {
    layoutPersistenceAdapter.prefetch?.({ kind: "workspace", workspaceId });
  }, []);

  // The hover peek popover (anchored beside the row) navigates to the workspace,
  // or to a specific agent when one of its agent rows is clicked.
  const handlePeekNavigate = useCallback(
    (workspaceId: string, agentId?: string): void => {
      if (agentId) {
        navigateToAgent(workspaceId, agentId);
        return;
      }
      handleWorkspaceClick(workspaceId);
    },
    [navigateToAgent, handleWorkspaceClick],
  );

  const handleOpenHome = useCallback((): void => {
    ensurePseudoTab(HOME_TAB_ID);
    navigateToHome();
  }, [ensurePseudoTab, navigateToHome]);

  const handleOpenSettings = useCallback((): void => {
    ensurePseudoTab(SETTINGS_TAB_ID);
    navigateToGlobalSettings();
  }, [ensurePseudoTab, navigateToGlobalSettings]);

  const handleResize = useCallback(
    (nextSizePx: number): void => {
      setWidth(Math.max(MIN_SIDEBAR_WIDTH_PX, nextSizePx));
    },
    [setWidth],
  );

  // JSX and rendering logic
  if (isCollapsed) {
    return null;
  }

  return (
    // The sidebar is dense with tooltip triggers, and the tooltip primitive's
    // default skip-delay shows every SUBSEQUENT tooltip instantly while the
    // pointer roams — a hover across the nav lights up a trail of tooltips.
    // Scope a provider over the sidebar: a longer initial delay and no
    // skip-delay chaining, so tooltips only appear on a deliberate hover.
    // (Themes' <Tooltip> reads this provider — `radix-ui` is pinned to the
    // same instance @radix-ui/themes resolves.)
    <TooltipPrimitive.Provider delayDuration={1000} skipDelayDuration={0}>
      <aside className={styles.sidebar} style={{ width: `${width}px` }} data-testid={ElementIds.WORKSPACE_SIDEBAR}>
        {/* Window-controls gutter clears the macOS traffic lights, then the
          collapse toggle. */}
        <div className={styles.windowControls} style={{ paddingLeft: getTitleBarLeftPadding(true) }}>
          <Tooltip content="Collapse sidebar" side="right">
            <IconButton
              variant="ghost"
              size="1"
              color="gray"
              className={styles.noDrag}
              onClick={() => setCollapsed(true)}
              aria-label="Collapse sidebar"
              data-testid={ElementIds.SIDEBAR_COLLAPSE_TOGGLE}
            >
              <PanelLeftClose size={16} />
            </IconButton>
          </Tooltip>
        </div>

        <nav className={styles.topActions}>
          <NavItem
            icon={Home}
            label="Home"
            isActive={isHomeRoute}
            onClick={handleOpenHome}
            testId={ElementIds.SIDEBAR_HOME_LINK}
          />
          {/* Commands (Cmd+K) and New Workspace are inert until the first
            workspace exists: the palette open-path is gated by
            `areGlobalShortcutsDisabledAtom` and the new-workspace modal isn't
            mounted on the first-run page. Reflect that with a real disabled
            state + tooltip rather than a silent no-op — the inline first-run
            form is the create affordance while the list is empty. */}
          <NavItem
            icon={Command}
            label="Commands"
            disabled={isWorkspaceListEmpty}
            disabledTooltip="Create a workspace to enable commands"
            onClick={toggleCommandPalette}
            testId={ElementIds.SIDEBAR_CMDK_LINK}
          />
          {/* Opens the new-workspace dialog; the per-repo "+" in the repo groups
            below is the direct-create affordance. */}
          <NavItem
            icon={Plus}
            label="New Workspace"
            disabled={isWorkspaceListEmpty}
            disabledTooltip="Use the form to create your first workspace"
            onClick={() => setNewWorkspaceDialog({ open: true })}
            testId={ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON}
          />
        </nav>

        <div className={styles.repoList}>
          {/* Empty first-run repo area. `repoGroups` is built from workspaces, so
            it's empty here — SidebarEmptyState renders from `projects`
            instead. */}
          {isWorkspaceListEmpty ? (
            <SidebarEmptyState projects={projects} onAddRepo={() => setIsAddRepoDialogOpen(true)} />
          ) : null}
          {repoGroups.map((group) => (
            <SidebarRepoGroup
              key={group.projectId}
              group={group}
              actions={workspaceActions}
              openInRuntime={openInRuntime}
              onWorkspaceClick={handleWorkspaceClick}
              onWorkspaceHover={handleWorkspaceHover}
              onBeginDelete={setDeleteTarget}
            />
          ))}
        </div>

        <div className={styles.spacer} />

        <nav className={styles.bottomActions}>
          <NavItem
            icon={Settings}
            label="Settings"
            isActive={isSettingsRoute}
            onClick={handleOpenSettings}
            testId={ElementIds.SIDEBAR_SETTINGS_LINK}
          />
          <ReportProblemPopover>
            <button
              type="button"
              className={navItemStyles.navItem}
              aria-label="Report a bug"
              data-testid={ElementIds.SIDEBAR_REPORT_BUG}
            >
              <Bug size={16} className={navItemStyles.navIcon} />
              <span className={navItemStyles.navLabel}>Report a bug</span>
            </button>
          </ReportProblemPopover>
          <DevModeIndicator />
          <div className={styles.versionRow} data-testid={ElementIds.SIDEBAR_VERSION}>
            <VersionPopover />
          </div>
        </nav>

        <ResizeHandle
          axis="x"
          direction={1}
          variant="edge-overlay"
          getSize={() => width}
          onResize={handleResize}
          ariaLabel="Resize sidebar"
          ariaValueNow={Math.round(width)}
          ariaValueMin={MIN_SIDEBAR_WIDTH_PX}
          data-testid={ElementIds.SIDEBAR_RESIZE_HANDLE}
        />

        {/* Hover peek popover shared across rows (anchored beside the hovered row). */}
        <WorkspacePeekOverlay onNavigate={handlePeekNavigate} />

        {/* Destructive workspace delete is confirmed before the optimistic removal. */}
        <DeleteConfirmationDialog
          isOpen={deleteTarget !== null}
          onOpenChange={(open) => {
            if (!open) setDeleteTarget(null);
          }}
          entityType="workspace"
          entityName={deleteTarget?.description ?? ""}
          onConfirm={handleDeleteConfirm}
        />

        {/* Empty first-run "Add a repo" flow reuses the standard add-repo dialog. */}
        <AddRepoDialog open={isAddRepoDialogOpen} onOpenChange={setIsAddRepoDialogOpen} setToast={setAddRepoToast} />
        <Toast
          open={addRepoToast !== null}
          onOpenChange={(open) => !open && setAddRepoToast(null)}
          title={addRepoToast?.title}
          type={addRepoToast?.type}
        />
      </aside>
    </TooltipPrimitive.Provider>
  );
};
