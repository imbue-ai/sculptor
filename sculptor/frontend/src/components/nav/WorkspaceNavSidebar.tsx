import { IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { LucideIcon } from "lucide-react";
import { ChevronDown, ChevronRight, CircleHelp, Home, PanelLeftClose, Plus, Search, Settings } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import type { Workspace } from "~/api";
import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { agentIdsByWorkspaceAtom, ensurePseudoTabAtom, workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { useHelpDialog } from "~/common/state/hooks/useHelpDialog.ts";
import { useCommandPalette } from "~/components/CommandPalette";
import { collapsedRepoGroupsAtom, navSidebarCollapsedAtom } from "~/components/nav/navAtoms.ts";
import { computeWorkspaceDotStatus, EMPTY_WORKSPACE_DOT_STATUS, WorkspaceStatusDots } from "~/components/statusDot";
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
  const { workspaceId: activeWorkspaceId, isHomeRoute, isSettingsRoute } = useImbueLocation();

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
          testId="nav-new-workspace"
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
              </div>
              {!isRepoCollapsed &&
                group.workspaces.map((ws) => {
                  const status = workspaceStatuses.get(ws.objectId) ?? EMPTY_WORKSPACE_DOT_STATUS;
                  return (
                    <button
                      type="button"
                      key={ws.objectId}
                      className={`${styles.workspaceRow} ${ws.objectId === activeWorkspaceId ? styles.workspaceRowActive : ""}`}
                      onClick={() => handleWorkspaceClick(ws.objectId)}
                      data-testid={`nav-workspace-${ws.objectId}`}
                    >
                      <span className={styles.workspaceDot}>
                        <WorkspaceStatusDots status={status} />
                      </span>
                      <span className={styles.workspaceName}>{ws.description ?? "Untitled"}</span>
                    </button>
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
