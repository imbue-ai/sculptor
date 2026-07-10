import { DropdownMenu } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { ChevronDown, Folder, FolderPlus, House, Pencil, Plus, Settings, Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo, useState } from "react";

import type { Workspace } from "~/api";
import { useImbueLocation, useImbueNavigate } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { userEmailAtom } from "~/common/state/atoms/userConfig.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { useOptimisticWorkspaceDelete } from "~/common/state/hooks/useOptimisticWorkspaceDelete.ts";
import { useProject } from "~/common/state/hooks/useProjects.ts";
import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";
import { useWorkspaceRename } from "~/common/state/hooks/useWorkspaceRename.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { WorkspaceStatusDots } from "~/components/statusDot/StatusDot.tsx";
import { computeWorkspaceDotStatus } from "~/components/statusDot/statusUtils.ts";

import { useLongPress } from "./useLongPress.ts";
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

/** One workspace row — owns its branch lookup + status dot, like the desktop row.
 * Long-press (or right-click) opens a context menu to rename or delete. */
const DrawerWorkspaceRow = ({
  workspace,
  isCurrent,
  onSelect,
  onRequestDelete,
}: {
  workspace: Workspace;
  isCurrent: boolean;
  onSelect: () => void;
  onRequestDelete: (workspace: Workspace) => void;
}): ReactElement => {
  const tasks = useAtomValue(tasksArrayAtom);
  const branchInfo = useWorkspaceBranch(workspace.objectId);
  const dotStatus = useMemo(
    () => computeWorkspaceDotStatus((tasks ?? []).filter((t) => t.workspaceId === workspace.objectId)),
    [tasks, workspace.objectId],
  );
  const branch = branchInfo?.currentBranch ?? workspace.sourceBranch ?? "";
  const [isRenaming, setIsRenaming] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { handlers: longPress, consumeClick } = useLongPress(() => setIsMenuOpen(true));

  // The shared optimistic rename (same path as the desktop sidebar): the new
  // name shows immediately; a rejected write rolls back and toasts.
  const renameWorkspace = useWorkspaceRename();
  const handleRenameCommit = (newName: string): void => {
    setIsRenaming(false);
    renameWorkspace(workspace.objectId, newName);
  };

  const handleClick = (): void => {
    if (consumeClick()) return;
    onSelect();
  };

  const dot = (
    <span className={styles.workspaceDot}>
      <WorkspaceStatusDots status={dotStatus} size={8} />
    </span>
  );

  // While renaming, the row is a plain container (not a button) so the input
  // owns its own tap/typing without the row's select handler interfering.
  if (isRenaming) {
    return (
      <div className={`${styles.workspaceRow} ${isCurrent ? styles.current : ""}`}>
        {dot}
        <span className={styles.workspaceInfo}>
          <InlineRenameInput
            value={workspace.description ?? ""}
            onCommit={handleRenameCommit}
            onCancel={() => setIsRenaming(false)}
            isEditing={true}
            className={styles.renameInput}
          />
          {branch ? <span className={styles.workspaceBranch}>{branch}</span> : null}
        </span>
      </div>
    );
  }

  return (
    <div className={styles.rowWrap}>
      {/* Long-press opens this menu anchored to the row's start (not the finger).
          The trigger is an invisible full-row anchor; opening is driven by the
          long-press handler on the button below, never by tapping the anchor. */}
      <DropdownMenu.Root open={isMenuOpen} onOpenChange={setIsMenuOpen}>
        <DropdownMenu.Trigger>
          <span className={styles.menuAnchor} aria-hidden="true" />
        </DropdownMenu.Trigger>
        {/* Rename starts from an onSelect, and InlineRenameInput takes focus
            synchronously — suppress the menu's close-time focus restore or it
            steals focus back and the resulting blur cancels the rename
            (InlineRenameInput's documented contract). */}
        <DropdownMenu.Content
          align="start"
          side="bottom"
          variant="soft"
          className="mobileTheme"
          onCloseAutoFocus={(e): void => e.preventDefault()}
        >
          <DropdownMenu.Item onSelect={() => setIsRenaming(true)}>
            <Pencil size={16} /> Rename
          </DropdownMenu.Item>
          <DropdownMenu.Separator />
          <DropdownMenu.Item color="red" onSelect={() => onRequestDelete(workspace)}>
            <Trash2 size={16} /> Delete workspace
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
      <button
        type="button"
        className={`${styles.workspaceRow} ${isCurrent ? styles.current : ""}`}
        onClick={handleClick}
        aria-current={isCurrent}
        {...longPress}
      >
        {dot}
        <span className={styles.workspaceInfo}>
          <span className={styles.workspaceName}>{workspace.description?.trim() || "Workspace"}</span>
          {branch ? <span className={styles.workspaceBranch}>{branch}</span> : null}
        </span>
      </button>
    </div>
  );
};

/** A collapsible repo group. */
const DrawerRepoGroup = ({
  projectId,
  workspaces,
  currentWorkspaceID,
  onSelect,
  onRequestDelete,
  defaultExpanded,
}: {
  projectId: string;
  workspaces: ReadonlyArray<Workspace>;
  currentWorkspaceID: string;
  onSelect: (id: string) => void;
  onRequestDelete: (workspace: Workspace) => void;
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
              onRequestDelete={onRequestDelete}
            />
          ))
        : null}
    </div>
  );
};

/**
 * WorkspaceDrawer (D1-D6) — left drawer over the chat (dimmed backdrop lives in
 * the shell / home). Header: Sculptor wordmark + user avatar; Home / Settings
 * nav (the current route is highlighted). Workspaces are grouped by repo,
 * collapsible, each row a status dot + name + branch with the current one
 * highlighted. A full-width New workspace button is pinned at the bottom. Empty
 * state when there are no workspaces.
 */
export const WorkspaceDrawer = ({ isOpen, onClose, currentWorkspaceID }: WorkspaceDrawerProps): ReactElement => {
  const workspaceID = currentWorkspaceID ?? "";
  const { navigateToWorkspace, navigateToHome, navigateToGlobalSettings } = useImbueNavigate();
  const { isHomeRoute, isSettingsRoute } = useImbueLocation();
  const workspaces = useAtomValue(workspacesArrayAtom);
  const userEmail = useAtomValue(userEmailAtom);
  // Workspace creation goes through the shared new-workspace modal (the same
  // one every desktop entry point uses); there is no separate mobile page.
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);

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

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const { execute: executeDelete } = useOptimisticWorkspaceDelete({
    onNavigateAfterDelete: (deletedId: string): void => {
      // Only the currently-viewed workspace's deletion strands the view — send
      // it home. Deleting any other workspace just drops it from the list.
      if (deletedId === workspaceID) {
        onClose();
        navigateToHome();
      }
    },
  });
  const handleRequestDelete = (ws: Workspace): void => {
    setDeleteTarget({ id: ws.objectId, name: ws.description?.trim() || "Workspace" });
  };

  const handleDeleteConfirm = (): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
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
          className={`${styles.navItem} ${isHomeRoute ? styles.navCurrent : ""}`}
          onClick={() => {
            onClose();
            navigateToHome();
          }}
        >
          <House size={20} /> Home
        </button>
        <button
          type="button"
          className={`${styles.navItem} ${isSettingsRoute ? styles.navCurrent : ""}`}
          onClick={() => {
            onClose();
            navigateToGlobalSettings();
          }}
        >
          <Settings size={20} /> Settings
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
              onRequestDelete={handleRequestDelete}
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
          setNewWorkspaceModal({ open: true });
        }}
      >
        <Plus size={18} /> New workspace
      </button>

      <DeleteConfirmationDialog
        isOpen={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        entityType="workspace"
        entityName={deleteTarget?.name ?? ""}
        onConfirm={handleDeleteConfirm}
      />
    </aside>
  );
};
