import { IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Bug, Home, PanelLeftClose, Plus, Search, Settings } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import type { Workspace } from "~/api";
import { ElementIds } from "~/api";
import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { agentIdsByWorkspaceAtom, ensurePseudoTabAtom, workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { AddRepoDialog } from "~/components/add-repo/AddRepoDialog.tsx";
import { useCommandPalette } from "~/components/CommandPalette";
import { renamingWorkspaceIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { OpenInRuntime } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceActionRuntime } from "~/components/CommandPalette/contextActions/types.ts";
import { useGitAndOpenInRuntime } from "~/components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { buildWorkspaceActions } from "~/components/CommandPalette/contextActions/workspaceActions.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { sidebarCollapsedAtom, sidebarWidthAtom } from "~/components/layout/sidebarAtoms.ts";
import { isWorkspaceListEmptyAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { useCreateWorkspaceFromSidebar } from "~/components/newWorkspace/useCreateWorkspaceFromSidebar.ts";
import { ReportProblemPopover } from "~/components/ReportProblemPopover.tsx";
import { layoutPersistenceAdapter } from "~/components/sections/persistence/LocalStorageLayoutAdapter.ts";
import { ResizeHandle } from "~/components/sections/ResizeHandle.tsx";
import { Toast, type ToastContent } from "~/components/Toast.tsx";
import { useWorkspaceTabActions } from "~/components/useWorkspaceTabActions.ts";
import { VersionDisplay } from "~/components/VersionDisplay.tsx";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { WorkspacePeekOverlay } from "~/pages/workspace/components/WorkspacePeekOverlay.tsx";

import navItemStyles from "./NavItem.module.scss";
import { NavItem } from "./NavItem.tsx";
import { SidebarFirstRunState } from "./SidebarFirstRunState.tsx";
import type { RepoGroup } from "./SidebarRepoGroup.tsx";
import { SidebarRepoGroup } from "./SidebarRepoGroup.tsx";
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
  const workspaces = useAtomValue(workspacesArrayAtom);
  const projects = useAtomValue(projectsArrayAtom);
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const setRenamingWorkspaceId = useSetAtom(renamingWorkspaceIdAtom);
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
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
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

  // Group workspaces by repo (project). Every workspace has a projectId, but the
  // project record itself may not have loaded yet — those fall back to an "Other"
  // group *name* (see the `?? "Other"` below) so nothing disappears.
  const repoGroups = useMemo((): ReadonlyArray<RepoGroup> => {
    const projectsById = new Map(projects.map((project) => [project.objectId, project]));
    const byProject = new Map<string, Array<Workspace>>();
    for (const ws of workspaces ?? []) {
      const key = ws.projectId;
      const list = byProject.get(key) ?? [];
      list.push(ws);
      byProject.set(key, list);
    }
    return [...byProject.entries()]
      .map(([projectId, wsList]) => ({
        projectId,
        name: projectsById.get(projectId)?.name ?? "Other",
        workspaces: wsList.sort((a, b) => (a.description ?? "").localeCompare(b.description ?? "")),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [workspaces, projects]);

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
        {/* Search (Cmd+K) and New Workspace are inert until the first
            workspace exists: the palette open-path is gated by
            `areGlobalShortcutsDisabledAtom` and the new-workspace modal isn't
            mounted on the first-run page. Reflect that with a real disabled
            state + tooltip rather than a silent no-op — the inline first-run
            form is the create affordance while the list is empty. */}
        <NavItem
          icon={Search}
          label="Search"
          disabled={isWorkspaceListEmpty}
          disabledTooltip="Create a workspace to enable search"
          onClick={toggleCommandPalette}
          testId={ElementIds.SIDEBAR_CMDK_LINK}
        />
        {/* Direct-create reusing the last settings + a fresh auto branch;
            falls back to the dialog when there are no last settings yet. */}
        <NavItem
          icon={Plus}
          label="New Workspace"
          disabled={isCreating || isWorkspaceListEmpty}
          disabledTooltip="Use the form to create your first workspace"
          onClick={() => void createFromSidebar()}
          testId={ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON}
        />
      </nav>

      <div className={styles.repoList}>
        {/* Empty first-run repo area. `repoGroups` is built from workspaces, so
            it's empty here — SidebarFirstRunState renders from `projects`
            instead. */}
        {isWorkspaceListEmpty ? (
          <SidebarFirstRunState projects={projects} onAddRepo={() => setIsAddRepoDialogOpen(true)} />
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
        <div className={styles.versionRow} data-testid={ElementIds.SIDEBAR_VERSION}>
          <VersionDisplay />
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
  );
};
