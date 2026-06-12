import { ContextMenu, DropdownMenu, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { LucideIcon } from "lucide-react";
import {
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Home,
  MoreHorizontal,
  PanelLeftClose,
  Plus,
  Search,
  Settings,
  Trash2,
} from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

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
import { useHelpDialog } from "~/common/state/hooks/useHelpDialog.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { prefetchWorkspaceDataAtom } from "~/common/state/hooks/useWorkspacePrefetch.ts";
import { useCommandPalette } from "~/components/CommandPalette";
import {
  renamingWorkspaceIdAtom,
  workspaceDeleteTargetAtom,
} from "~/components/CommandPalette/contextActions/atoms.ts";
import {
  type OpenInRuntime,
  WorkspaceContextMenuContent,
  WorkspaceDropdownMenuContent,
} from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceActionRuntime } from "~/components/CommandPalette/contextActions/types.ts";
import { useGitAndOpenInRuntime } from "~/components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { buildWorkspaceActions } from "~/components/CommandPalette/contextActions/workspaceActions.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { collapsedRepoGroupsAtom, navSidebarCollapsedAtom } from "~/components/nav/navAtoms.ts";
import { computeWorkspaceDotStatus, EMPTY_WORKSPACE_DOT_STATUS, WorkspaceStatusDots } from "~/components/statusDot";
import { useWorkspaceTabActions } from "~/components/useWorkspaceTabActions.ts";
import { HOME_TAB_ID, SETTINGS_TAB_ID } from "~/components/workspaceTabIds.ts";
import { getTitleBarLeftPadding } from "~/electron/utils.ts";

import styles from "./WorkspaceNavSidebar.module.scss";

type NavItemProps = {
  icon: LucideIcon;
  label: string;
  active?: boolean;
  onClick: () => void;
  testId?: string;
};

const NavItem = ({ icon: Icon, label, active, onClick, testId }: NavItemProps): ReactElement => (
  <button
    type="button"
    className={`${styles.navItem} ${active ? styles.navItemActive : ""}`}
    onClick={onClick}
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
 * Vertical navigation sidebar — replaces the horizontal workspace tab bar and
 * the top-bar icon cluster (REQ-NAV-1..8). Top actions, then repos as
 * collapsible headers with their workspaces, then Settings + Help anchored to
 * the bottom with flexible space between. Collapsing hides it entirely; the
 * top bar then exposes the expand toggle (REQ-TOPBAR-5).
 */
export const WorkspaceNavSidebar = (): ReactElement | null => {
  const isCollapsed = useAtomValue(navSidebarCollapsedAtom);
  const setCollapsed = useSetAtom(navSidebarCollapsedAtom);
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);

  const workspaces = useAtomValue(workspacesArrayAtom);
  const projects = useAtomValue(projectsArrayAtom);
  const tasks = useAtomValue(tasksArrayAtom);
  const agentIdsByWorkspace = useAtomValue(agentIdsByWorkspaceAtom);
  const collapsedRepos = useAtomValue(collapsedRepoGroupsAtom);
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);

  const { navigateToWorkspace, navigateToAgent, navigateToAddWorkspace, navigateToHome, navigateToGlobalSettings } =
    useImbueNavigate();
  const { toggle: toggleCommandPalette } = useCommandPalette();
  const { showHelpDialog } = useHelpDialog();
  const openSettings = useOpenSettings();
  const { workspaceId: activeWorkspaceId, isHomeRoute, isSettingsRoute } = useImbueLocation();

  // Right-click context menu on workspace rows — same action registry as the
  // old tab strip and Cmd+K → Workspace actions. The delete-confirmation
  // dialog itself is rendered by the headless WorkspaceTabs in PageLayout,
  // driven by the shared workspaceDeleteTargetAtom.
  const dangerColor = useThemeDangerColor();
  const effectiveOpenTabIds = useAtomValue(effectiveOpenTabIdsAtom);
  const { handleClose, handleCloseOthers, handleCloseAll } = useWorkspaceTabActions();
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const setDeleteTarget = useSetAtom(workspaceDeleteTargetAtom);
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

  const workspaceStatuses = useMemo(() => {
    const statusMap = new Map<string, ReturnType<typeof computeWorkspaceDotStatus>>();
    const activeTasks = tasks ?? [];
    for (const workspace of workspaces ?? []) {
      const workspaceTasks = activeTasks.filter((task) => task.workspaceId === workspace.objectId);
      statusMap.set(workspace.objectId, computeWorkspaceDotStatus(workspaceTasks));
    }
    return statusMap;
  }, [workspaces, tasks]);

  // Group workspaces by repo (project). Workspaces whose project hasn't loaded
  // yet fall into an "Other" bucket so nothing disappears.
  const repoGroups = useMemo((): ReadonlyArray<RepoGroup> => {
    const projectsById = new Map(projects.map((p) => [p.objectId, p]));
    const byProject = new Map<string, Array<Workspace>>();
    for (const ws of workspaces ?? []) {
      const key = ws.projectId ?? "__unknown__";
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

  // Hovering a row warms that workspace's git caches so a follow-up click
  // renders from cache. Open tabs are already prefetched on hydration
  // (usePrefetchOpenWorkspaces); this mostly helps closed workspaces.
  const prefetchWorkspaceData = useSetAtom(prefetchWorkspaceDataAtom);
  const handleWorkspaceHover = useCallback(
    (workspaceId: string): void => {
      prefetchWorkspaceData(workspaceId);
    },
    [prefetchWorkspaceData],
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

  if (isCollapsed) return null;

  return (
    <aside className={styles.sidebar} data-testid="workspace-nav-sidebar">
      {/* Window-controls gutter + sidebar toggle (REQ-NAV-7) */}
      <div className={styles.windowControls} style={{ paddingLeft: getTitleBarLeftPadding(true) }}>
        <Tooltip content="Collapse sidebar" side="right">
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            className={styles.noDrag}
            onClick={() => setCollapsed(true)}
            aria-label="Collapse sidebar"
            data-testid="nav-sidebar-toggle"
          >
            <PanelLeftClose size={16} />
          </IconButton>
        </Tooltip>
      </div>

      <nav className={styles.topActions}>
        <NavItem icon={Home} label="Home" active={isHomeRoute} onClick={handleOpenHome} testId="nav-home" />
        <NavItem icon={Search} label="Search" onClick={toggleCommandPalette} testId="nav-search" />
        <NavItem
          icon={Plus}
          label="New Workspace"
          onClick={() => navigateToAddWorkspace()}
          testId={ElementIds.ADD_WORKSPACE_BUTTON}
        />
      </nav>

      <div className={styles.repoList}>
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
                  data-testid={`nav-repo-${group.projectId}`}
                >
                  <Chevron size={16} className={styles.repoChevron} />
                  <Text className={styles.repoName} truncate>
                    {group.name}
                  </Text>
                </button>
                <span className={styles.rowActions}>
                  <Tooltip content="Repository settings" side="right">
                    <IconButton
                      variant="ghost"
                      size="1"
                      color="gray"
                      className={styles.hoverReveal}
                      onClick={() => openSettings("repositories", group.projectId)}
                      aria-label="Repository settings"
                      data-testid={`nav-repo-settings-${group.projectId}`}
                    >
                      <Settings size={13} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip content="New workspace in this repo" side="right">
                    <IconButton
                      variant="ghost"
                      size="1"
                      color="gray"
                      onClick={() => navigateToAddWorkspace()}
                      aria-label="New workspace in this repo"
                      data-testid={`nav-repo-add-${group.projectId}`}
                    >
                      <Plus size={13} />
                    </IconButton>
                  </Tooltip>
                </span>
              </div>
              {!isRepoCollapsed &&
                group.workspaces.map((ws) => {
                  const status = workspaceStatuses.get(ws.objectId) ?? EMPTY_WORKSPACE_DOT_STATUS;
                  const isRenaming = renamingWorkspaceId === ws.objectId;
                  return (
                    <ContextMenu.Root key={ws.objectId}>
                      <ContextMenu.Trigger>
                        {/* data-workspace-tab + data-tab-id make the row a
                            hover target for the shared WorkspacePeekOverlay;
                            data-peek-side opens the peek beside the row. */}
                        <div
                          className={`${styles.workspaceRow} ${ws.objectId === activeWorkspaceId ? styles.workspaceRowActive : ""}`}
                          data-workspace-tab=""
                          data-tab-id={ws.objectId}
                          data-peek-side="right"
                        >
                          {isRenaming ? (
                            <span className={styles.workspaceRowButton}>
                              <span className={styles.workspaceDot}>
                                <WorkspaceStatusDots status={status} />
                              </span>
                              <InlineRenameInput
                                value={ws.description ?? ""}
                                onCommit={(newName) => void handleRenameCommit(ws.objectId, newName)}
                                onCancel={() => setRenamingWorkspaceId(null)}
                                isEditing={true}
                              />
                            </span>
                          ) : (
                            <button
                              type="button"
                              className={styles.workspaceRowButton}
                              onClick={() => handleWorkspaceClick(ws.objectId)}
                              onPointerEnter={() => handleWorkspaceHover(ws.objectId)}
                              data-testid={ElementIds.WORKSPACE_TAB}
                              data-has-unread={String(status.hasUnread)}
                            >
                              <span className={styles.workspaceDot}>
                                <WorkspaceStatusDots status={status} />
                              </span>
                              <span className={styles.workspaceName}>{ws.description ?? "Untitled"}</span>
                            </button>
                          )}
                          <span className={`${styles.rowActions} ${styles.hoverReveal}`}>
                            <DropdownMenu.Root>
                              <Tooltip content="Workspace actions" side="bottom">
                                <DropdownMenu.Trigger>
                                  <IconButton
                                    variant="ghost"
                                    size="1"
                                    color="gray"
                                    aria-label="Workspace actions"
                                    data-testid={`nav-workspace-menu-${ws.objectId}`}
                                  >
                                    <MoreHorizontal size={13} />
                                  </IconButton>
                                </DropdownMenu.Trigger>
                              </Tooltip>
                              <WorkspaceDropdownMenuContent
                                actions={workspaceActions}
                                workspace={ws}
                                destructiveColor={dangerColor}
                                openInRuntime={openInRuntime}
                              />
                            </DropdownMenu.Root>
                            <Tooltip content="Delete workspace" side="bottom">
                              <IconButton
                                variant="ghost"
                                size="1"
                                color="gray"
                                onClick={() => setDeleteTarget({ id: ws.objectId, name: ws.description ?? "" })}
                                aria-label="Delete workspace"
                                data-testid={`nav-workspace-delete-${ws.objectId}`}
                              >
                                <Trash2 size={13} />
                              </IconButton>
                            </Tooltip>
                          </span>
                        </div>
                      </ContextMenu.Trigger>
                      <WorkspaceContextMenuContent
                        actions={workspaceActions}
                        workspace={ws}
                        destructiveColor={dangerColor}
                        openInRuntime={openInRuntime}
                      />
                    </ContextMenu.Root>
                  );
                })}
            </div>
          );
        })}
      </div>

      <div className={styles.spacer} />

      <nav className={styles.bottomActions}>
        <NavItem
          icon={Settings}
          label="Settings"
          active={isSettingsRoute}
          onClick={handleOpenSettings}
          testId="nav-settings"
        />
        <NavItem icon={CircleHelp} label="Help" onClick={showHelpDialog} testId="nav-help" />
      </nav>
    </aside>
  );
};
