import { useAtomValue } from "jotai";
import { ChevronDown, CirclePlus, Folder, FolderPlus, House } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo, useState } from "react";

import type { Workspace } from "~/api";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { userEmailAtom } from "~/common/state/atoms/userConfig.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { useProject } from "~/common/state/hooks/useProjects.ts";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";
import { WorkspaceStatusDots } from "~/components/statusDot/StatusDot.tsx";
import { computeWorkspaceDotStatus } from "~/components/statusDot/statusUtils.ts";

import styles from "./WorkspaceDrawer.module.scss";

type WorkspaceDrawerProps = {
  isOpen: boolean;
  onClose: () => void;
  /** The workspace to highlight as current; undefined on the landing route. */
  currentWorkspaceID?: string;
};

function getInitials(email: string | undefined): string {
  if (!email) return "?";
  const local = email.split("@")[0] ?? "";
  const parts = local.split(/[.\-_]/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase() || "?";
}

/** One workspace row — owns its branch lookup + status dot, like the desktop row. */
const DrawerWorkspaceRow = ({
  workspace,
  isCurrent,
  onSelect,
}: {
  workspace: Workspace;
  isCurrent: boolean;
  onSelect: () => void;
}): ReactElement => {
  const tasks = useAtomValue(tasksArrayAtom);
  const branchInfo = useWorkspaceBranch(workspace.objectId);
  const dotStatus = useMemo(
    () => computeWorkspaceDotStatus((tasks ?? []).filter((t) => t.workspaceId === workspace.objectId)),
    [tasks, workspace.objectId],
  );
  const branch = branchInfo?.currentBranch ?? workspace.sourceBranch ?? "";

  return (
    <button
      type="button"
      className={`${styles.workspaceRow} ${isCurrent ? styles.current : ""}`}
      onClick={onSelect}
      aria-current={isCurrent}
    >
      <span className={styles.workspaceDot}>
        <WorkspaceStatusDots status={dotStatus} size={8} />
      </span>
      <span className={styles.workspaceInfo}>
        <span className={styles.workspaceName}>{workspace.description?.trim() || "Workspace"}</span>
        {branch ? <span className={styles.workspaceBranch}>{branch}</span> : null}
      </span>
    </button>
  );
};

/** A collapsible repo group. */
const DrawerRepoGroup = ({
  projectId,
  workspaces,
  currentWorkspaceID,
  onSelect,
  defaultExpanded,
}: {
  projectId: string;
  workspaces: ReadonlyArray<Workspace>;
  currentWorkspaceID: string;
  onSelect: (id: string) => void;
  defaultExpanded: boolean;
}): ReactElement => {
  const project = useProject(projectId);
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className={styles.repoGroup}>
      <button
        type="button"
        className={`${styles.repoHeader} ${isExpanded ? "" : styles.collapsed}`}
        onClick={() => setIsExpanded((v) => !v)}
        aria-expanded={isExpanded}
      >
        <ChevronDown size={16} className={styles.chevron} />
        <Folder size={16} className={styles.repoFolder} />
        <span className={styles.repoName}>{project?.name ?? "Repository"}</span>
        <span className={styles.repoCount}>{workspaces.length}</span>
      </button>
      {isExpanded
        ? workspaces.map((ws) => (
            <DrawerWorkspaceRow
              key={ws.objectId}
              workspace={ws}
              isCurrent={ws.objectId === currentWorkspaceID}
              onSelect={() => onSelect(ws.objectId)}
            />
          ))
        : null}
    </div>
  );
};

/**
 * WorkspaceDrawer (D1-D6) — left drawer over the chat (dimmed backdrop lives in
 * the shell). Header: Sculptor wordmark + user avatar; Home / Workspaces nav.
 * Workspaces are grouped by repo, collapsible, each row a status dot + name +
 * branch with the current one highlighted. A full-width New workspace button is
 * pinned at the bottom. Empty state when there are no workspaces.
 */
export const WorkspaceDrawer = ({ isOpen, onClose, currentWorkspaceID }: WorkspaceDrawerProps): ReactElement => {
  const workspaceID = currentWorkspaceID ?? "";
  const { navigateToWorkspace, navigateToHome, navigateToAddWorkspace } = useImbueNavigate();
  const workspaces = useAtomValue(workspacesArrayAtom);
  const userEmail = useAtomValue(userEmailAtom);

  const groups = useMemo(() => {
    const byProject = new Map<string, Array<Workspace>>();
    for (const ws of workspaces ?? []) {
      const list = byProject.get(ws.projectId) ?? [];
      list.push(ws);
      byProject.set(ws.projectId, list);
    }
    return [...byProject.entries()];
  }, [workspaces]);

  const isEmpty = (workspaces ?? []).length === 0;

  const handleSelect = (id: string): void => {
    onClose();
    navigateToWorkspace(id);
  };

  return (
    <aside className={`${styles.drawer} ${isOpen ? styles.open : ""}`} aria-hidden={!isOpen}>
      <div className={styles.header}>
        <span className={styles.wordmark}>Sculptor</span>
        <span className={styles.avatar}>{getInitials(userEmail)}</span>
      </div>

      <nav className={styles.nav}>
        <button
          type="button"
          className={styles.navItem}
          onClick={() => {
            onClose();
            navigateToHome();
          }}
        >
          <House size={20} /> Home
        </button>
        <button type="button" className={`${styles.navItem} ${styles.navCurrent}`}>
          <Folder size={20} /> Workspaces
        </button>
      </nav>

      <div className={styles.workspaceList}>
        {isEmpty ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>
              <FolderPlus size={28} />
            </span>
            <span className={styles.emptyTitle}>No workspaces yet</span>
            <span className={styles.emptyDesc}>Create your first workspace to start an agent on a fresh branch.</span>
          </div>
        ) : (
          groups.map(([projectId, wsList]) => (
            <DrawerRepoGroup
              key={projectId}
              projectId={projectId}
              workspaces={wsList}
              currentWorkspaceID={workspaceID}
              onSelect={handleSelect}
              defaultExpanded={wsList.some((ws) => ws.objectId === workspaceID) || groups.length === 1}
            />
          ))
        )}
      </div>

      <button
        type="button"
        className={styles.newWorkspace}
        onClick={() => {
          onClose();
          navigateToAddWorkspace();
        }}
      >
        <CirclePlus size={18} /> New workspace
      </button>
    </aside>
  );
};
