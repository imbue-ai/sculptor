import { ContextMenu, DropdownMenu, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { LucideIcon } from "lucide-react";
import {
  Bug,
  ChevronDown,
  ChevronRight,
  FolderPlus,
  Home,
  MoreHorizontal,
  PanelLeftClose,
  Plus,
  Search,
  Settings,
  Trash2,
} from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import type { Workspace } from "~/api";
import { ElementIds, updateWorkspace } from "~/api";
import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import {
  agentIdsByWorkspaceAtom,
  effectiveOpenTabIdsAtom,
  ensurePseudoTabAtom,
  workspacesArrayAtom,
} from "~/common/state/atoms/workspaces.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { AddRepoDialog } from "~/components/add-repo/AddRepoDialog.tsx";
import { useCommandPalette } from "~/components/CommandPalette";
import { renamingWorkspaceIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { type OpenInRuntime, WorkspaceContextMenuContent } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceAction, WorkspaceActionRuntime } from "~/components/CommandPalette/contextActions/types.ts";
import { useGitAndOpenInRuntime } from "~/components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { buildWorkspaceActions } from "~/components/CommandPalette/contextActions/workspaceActions.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { sidebarCollapsedAtom, sidebarWidthAtom } from "~/components/layout/sidebarAtoms.ts";
import { collapsedRepoGroupsAtom } from "~/components/nav/navAtoms.ts";
import { isWorkspaceListEmptyAtom, newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { useCreateWorkspaceFromSidebar } from "~/components/newWorkspace/useCreateWorkspaceFromSidebar.ts";
import { ReportProblemPopover } from "~/components/ReportProblemPopover.tsx";
import { layoutPersistenceAdapter } from "~/components/sections/persistence/LocalStorageLayoutAdapter.ts";
import { ResizeHandle } from "~/components/sections/ResizeHandle.tsx";
import { computeWorkspaceDotStatus, EMPTY_WORKSPACE_DOT_STATUS, WorkspaceStatusDots } from "~/components/statusDot";
import { Toast, type ToastContent } from "~/components/Toast.tsx";
import { useWorkspaceTabActions } from "~/components/useWorkspaceTabActions.ts";
import { VersionDisplay } from "~/components/VersionDisplay.tsx";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";
import { WorkspacePeekOverlay } from "~/pages/workspace/components/WorkspacePeekOverlay.tsx";

import styles from "./WorkspaceSidebar.module.scss";

/** Smallest sidebar width the resize handle allows, in pixels. */
const MIN_SIDEBAR_WIDTH_PX = 180;

type NavItemProps = {
  icon: LucideIcon;
  label: string;
  isActive?: boolean;
  disabled?: boolean;
  onClick: () => void;
  testId?: string;
};

const NavItem = ({ icon: Icon, label, isActive, disabled, onClick, testId }: NavItemProps): ReactElement => (
  <button
    type="button"
    className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
    onClick={onClick}
    disabled={disabled}
    data-testid={testId}
  >
    <Icon size={16} className={styles.navIcon} />
    <span className={styles.navLabel}>{label}</span>
  </button>
);

type RepoGroup = {
  projectId: string;
  name: string;
  workspaces: ReadonlyArray<Workspace>;
};

/**
 * The compact "..." dropdown menu for a workspace row. Reuses the shared
 * `workspaceActions` descriptors so it stays in sync with the right-click
 * context menu and Cmd+K, but renders the flat action list (without the
 * right-click menu's "Open in..." submenu and copy group) so the hover-
 * revealed button stays light.
 */
const WorkspaceRowDropdownItems = ({
  actions,
  workspace,
  destructiveColor,
}: {
  actions: ReadonlyArray<WorkspaceAction>;
  workspace: Workspace;
  destructiveColor: ReturnType<typeof useThemeDangerColor>;
}): ReactElement => (
  <DropdownMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
    {actions
      .filter((action) => (action.visible ? action.visible(workspace) : true))
      .map((action) => (
        <DropdownMenu.Item
          key={action.id}
          data-testid={action.testId}
          color={action.destructive ? destructiveColor : undefined}
          disabled={action.disabled ? action.disabled(workspace) : false}
          onSelect={(): void => void action.perform(workspace)}
        >
          {action.icon ? <action.icon size={14} /> : null} {action.getTitle ? action.getTitle(workspace) : action.title}
        </DropdownMenu.Item>
      ))}
  </DropdownMenu.Content>
);

/**
 * A single workspace row in the sidebar repo group: the status dot + name (or an
 * inline rename input while renaming), the hover-revealed actions dropdown and
 * delete button, and the wrapping right-click context menu. Purely presentational
 * — all behavior is delegated through the callback props.
 */
const SidebarWorkspaceRow = ({
  workspace,
  status,
  isRenaming,
  isActive,
  actions,
  openInRuntime,
  destructiveColor,
  onClick,
  onHover,
  onRenameCommit,
  onRenameCancel,
  onBeginDelete,
}: {
  workspace: Workspace;
  status: ReturnType<typeof computeWorkspaceDotStatus>;
  isRenaming: boolean;
  isActive: boolean;
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
  destructiveColor: ReturnType<typeof useThemeDangerColor>;
  onClick: () => void;
  onHover: () => void;
  onRenameCommit: (newName: string) => void;
  onRenameCancel: () => void;
  onBeginDelete: () => void;
}): ReactElement => (
  <ContextMenu.Root>
    <ContextMenu.Trigger>
      <div className={`${styles.workspaceRow} ${isActive ? styles.workspaceRowActive : ""}`}>
        {isRenaming ? (
          <span className={styles.workspaceRowButton}>
            <span className={styles.workspaceDot}>
              <WorkspaceStatusDots status={status} />
            </span>
            <InlineRenameInput
              value={workspace.description ?? ""}
              onCommit={onRenameCommit}
              onCancel={onRenameCancel}
              isEditing={true}
            />
          </span>
        ) : (
          <button
            type="button"
            className={styles.workspaceRowButton}
            onClick={onClick}
            onMouseEnter={onHover}
            data-testid={ElementIds.SIDEBAR_WORKSPACE_ROW}
            data-workspace-id={workspace.objectId}
            data-has-unread={String(status.hasUnread)}
            data-workspace-tab
            data-tab-id={workspace.objectId}
          >
            <span className={styles.workspaceDot}>
              <WorkspaceStatusDots status={status} />
            </span>
            <span className={styles.workspaceName}>{workspace.description ?? "Untitled"}</span>
          </button>
        )}
        <Flex className={`${styles.rowActions} ${styles.hoverReveal}`} gap="2">
          <DropdownMenu.Root>
            <Tooltip content="Workspace actions" side="bottom">
              <DropdownMenu.Trigger>
                <IconButton
                  variant="ghost"
                  size="1"
                  color="gray"
                  aria-label="Workspace actions"
                  data-testid={ElementIds.SIDEBAR_WORKSPACE_ROW_MENU}
                  data-workspace-id={workspace.objectId}
                >
                  <MoreHorizontal size={13} />
                </IconButton>
              </DropdownMenu.Trigger>
            </Tooltip>
            <WorkspaceRowDropdownItems actions={actions} workspace={workspace} destructiveColor={destructiveColor} />
          </DropdownMenu.Root>
          <Tooltip content="Delete workspace" side="bottom">
            <IconButton
              variant="ghost"
              size="1"
              color="gray"
              onClick={onBeginDelete}
              aria-label="Delete workspace"
              data-testid={ElementIds.SIDEBAR_WORKSPACE_ROW_DELETE}
              data-workspace-id={workspace.objectId}
            >
              <Trash2 size={13} />
            </IconButton>
          </Tooltip>
        </Flex>
      </div>
    </ContextMenu.Trigger>
    <WorkspaceContextMenuContent
      actions={actions}
      workspace={workspace}
      destructiveColor={destructiveColor}
      openInRuntime={openInRuntime}
    />
  </ContextMenu.Root>
);

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
  const tasks = useAtomValue(tasksArrayAtom);
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const collapsedRepos = useAtomValue(collapsedRepoGroupsAtom);
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);
  const effectiveOpenTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
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
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
  const { toggle: toggleCommandPalette } = useCommandPalette();
  const openSettings = useOpenSettings();
  const { workspaceId: activeWorkspaceId, isHomeRoute, isSettingsRoute } = useImbueLocation();
  const dangerColor = useThemeDangerColor();
  const { handleClose, handleCloseOthers, handleCloseAll, navigateToNextTab } = useWorkspaceTabActions();
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

  const workspaceActionRuntime = useMemo<WorkspaceActionRuntime>(
    () => ({
      beginRename: (ws): void => setRenamingWorkspaceId(ws.objectId),
      closeWorkspace: (ws): void => handleClose(ws.objectId),
      closeOtherWorkspaces: (ws): void => handleCloseOthers(ws.objectId),
      closeAllWorkspaces: (): void => handleCloseAll(),
      beginDelete: (ws): void => setDeleteTarget(ws),
      canCloseOthers: (): boolean => effectiveOpenTabIds.length > 1,
      ...gitAndOpenIn,
    }),
    [setRenamingWorkspaceId, handleClose, handleCloseOthers, handleCloseAll, effectiveOpenTabIds.length, gitAndOpenIn],
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

  const workspaceStatuses = useMemo(() => {
    const statusMap = new Map<string, ReturnType<typeof computeWorkspaceDotStatus>>();
    const activeTasks = tasks ?? [];
    for (const workspace of workspaces ?? []) {
      const workspaceTasks = activeTasks.filter((task) => task.workspaceId === workspace.objectId);
      statusMap.set(workspace.objectId, computeWorkspaceDotStatus(workspaceTasks));
    }
    return statusMap;
  }, [workspaces, tasks]);

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

  const toggleRepo = useCallback(
    (projectId: string): void => {
      setCollapsedRepos((prev) => ({ ...prev, [projectId]: !(prev[projectId] ?? false) }));
    },
    [setCollapsedRepos],
  );

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
        <NavItem icon={Search} label="Search" onClick={toggleCommandPalette} testId={ElementIds.SIDEBAR_CMDK_LINK} />
        {/* Direct-create reusing the last settings + a fresh auto branch;
            falls back to the dialog when there are no last settings yet. */}
        <NavItem
          icon={Plus}
          label="New Workspace"
          disabled={isCreating}
          onClick={() => void createFromSidebar()}
          testId={ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON}
        />
      </nav>

      <div className={styles.repoList}>
        {/* Empty first-run repo area. With no repos, an "Add a repo"
            button; with repos but no workspaces, each repo header followed by a
            "No workspaces yet" hint. `repoGroups` is built from workspaces, so
            it's empty here — render from `projects` instead. */}
        {isWorkspaceListEmpty ? (
          projects.length === 0 ? (
            <NavItem
              icon={FolderPlus}
              label="Add a repo"
              onClick={() => setIsAddRepoDialogOpen(true)}
              testId={ElementIds.SIDEBAR_ADD_REPO_BUTTON}
            />
          ) : (
            projects.map((project) => (
              <div key={project.objectId} className={styles.repoGroup}>
                <div className={styles.repoHeader}>
                  <span className={styles.repoHeaderButton}>
                    <Text className={styles.repoName} truncate>
                      {project.name}
                    </Text>
                  </span>
                </div>
                <Text className={styles.noWorkspacesHint} data-testid={ElementIds.SIDEBAR_NO_WORKSPACES_HINT}>
                  No workspaces yet
                </Text>
              </div>
            ))
          )
        ) : null}
        {repoGroups.map((group) => {
          const isRepoCollapsed = collapsedRepos[group.projectId] ?? false;
          const Chevron = isRepoCollapsed ? ChevronRight : ChevronDown;
          return (
            <div key={group.projectId} className={styles.repoGroup}>
              <div className={styles.repoHeader}>
                <button
                  type="button"
                  className={styles.repoHeaderButton}
                  onClick={() => toggleRepo(group.projectId)}
                  data-testid={ElementIds.SIDEBAR_REPO_GROUP}
                  data-project-id={group.projectId}
                >
                  <Chevron size={16} className={styles.repoChevron} />
                  <Text className={styles.repoName} truncate>
                    {group.name}
                  </Text>
                </button>
                <Flex className={styles.rowActions} gap="2">
                  <Tooltip content="Repository settings" side="right">
                    <IconButton
                      variant="ghost"
                      size="1"
                      color="gray"
                      className={styles.hoverReveal}
                      onClick={() => openSettings("repositories", group.projectId)}
                      aria-label="Repository settings"
                      data-testid={ElementIds.SIDEBAR_REPO_SETTINGS}
                      data-project-id={group.projectId}
                    >
                      <Settings size={13} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip content="New workspace in this repo" side="right">
                    {/* Open the dialog pre-selecting this repo. */}
                    <IconButton
                      variant="ghost"
                      size="1"
                      color="gray"
                      onClick={() => setNewWorkspaceModal({ open: true, presetProjectId: group.projectId })}
                      aria-label="New workspace in this repo"
                      data-testid={ElementIds.SIDEBAR_REPO_ADD_WORKSPACE}
                      data-project-id={group.projectId}
                    >
                      <Plus size={13} />
                    </IconButton>
                  </Tooltip>
                </Flex>
              </div>
              {!isRepoCollapsed &&
                group.workspaces.map((ws) => (
                  <SidebarWorkspaceRow
                    key={ws.objectId}
                    workspace={ws}
                    status={workspaceStatuses.get(ws.objectId) ?? EMPTY_WORKSPACE_DOT_STATUS}
                    isRenaming={renamingWorkspaceId === ws.objectId}
                    isActive={ws.objectId === activeWorkspaceId}
                    actions={workspaceActions}
                    openInRuntime={openInRuntime}
                    destructiveColor={dangerColor}
                    onClick={() => handleWorkspaceClick(ws.objectId)}
                    onHover={() => handleWorkspaceHover(ws.objectId)}
                    onRenameCommit={(newName) => void handleRenameCommit(ws.objectId, newName)}
                    onRenameCancel={() => setRenamingWorkspaceId(null)}
                    onBeginDelete={() => setDeleteTarget(ws)}
                  />
                ))}
            </div>
          );
        })}
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
        <Flex align="center" justify="between" className={styles.bottomMeta} gap="2">
          <ReportProblemPopover>
            <button
              type="button"
              className={styles.reportBugButton}
              aria-label="Report a bug"
              data-testid={ElementIds.SIDEBAR_REPORT_BUG}
            >
              <Bug size={14} className={styles.navIcon} />
              <span className={styles.navLabel}>Report a bug</span>
            </button>
          </ReportProblemPopover>
          <span className={styles.versionWrapper} data-testid={ElementIds.SIDEBAR_VERSION}>
            <VersionDisplay />
          </span>
        </Flex>
      </nav>

      <ResizeHandle
        axis="x"
        direction={1}
        getSize={() => width}
        onResize={handleResize}
        className={styles.resizeHandle}
        ariaLabel="Resize sidebar"
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
