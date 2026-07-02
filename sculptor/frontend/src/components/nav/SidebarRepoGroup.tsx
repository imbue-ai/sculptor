// One collapsible repo group in the workspace sidebar: the repo header row (collapse
// chevron, hover-revealed repository settings, and an always-visible "+" that opens
// the new-workspace dialog pre-scoped to this repo), followed by one row per
// workspace while expanded. Cross-group concerns — building the groups, the shared
// action list, and the delete confirmation — stay in WorkspaceSidebar and arrive as
// props; per-group state (collapse, rename) is read from its atoms here.

import { ContextMenu, DropdownMenu, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { ChevronDown, ChevronRight, MoreHorizontal, Plus, Settings, Trash2 } from "lucide-react";
import type { ReactElement } from "react";

import type { Workspace } from "~/api";
import { ElementIds, updateWorkspace } from "~/api";
import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { renamingWorkspaceIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import {
  type OpenInRuntime,
  WorkspaceContextMenuContent,
  WorkspaceDropdownMenuContent,
} from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceAction } from "~/components/CommandPalette/contextActions/types.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import type { WorkspaceDotStatus } from "~/components/statusDot";
import { EMPTY_WORKSPACE_DOT_STATUS, WorkspaceStatusDots } from "~/components/statusDot";

import { collapsedRepoGroupsAtom } from "./navAtoms.ts";
import styles from "./SidebarRepoGroup.module.scss";

// A repo (project) and the workspaces that live in it, as grouped by
// WorkspaceSidebar.
export type RepoGroup = {
  projectId: string;
  name: string;
  workspaces: ReadonlyArray<Workspace>;
};

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
  status: WorkspaceDotStatus;
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
            <WorkspaceDropdownMenuContent
              actions={actions}
              workspace={workspace}
              destructiveColor={destructiveColor}
              openInRuntime={openInRuntime}
            />
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

type SidebarRepoGroupProps = {
  group: RepoGroup;
  // Per-workspace dot status, computed once for the whole sidebar.
  statuses: ReadonlyMap<string, WorkspaceDotStatus>;
  // The shared workspace action list (rename/delete/git/open-in), built once in
  // WorkspaceSidebar so every group and the command palette agree on the entries.
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
  onWorkspaceClick: (workspaceId: string) => void;
  onWorkspaceHover: (workspaceId: string) => void;
  // Delete is confirmed by a dialog owned by WorkspaceSidebar (shared across
  // groups), so beginning one hands the target back up.
  onBeginDelete: (workspace: Workspace) => void;
};

export const SidebarRepoGroup = ({
  group,
  statuses,
  actions,
  openInRuntime,
  onWorkspaceClick,
  onWorkspaceHover,
  onBeginDelete,
}: SidebarRepoGroupProps): ReactElement => {
  // External atoms
  const collapsedRepos = useAtomValue(collapsedRepoGroupsAtom);
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const setNewWorkspaceModal = useSetAtom(newWorkspaceModalAtom);

  // External hooks
  const openSettings = useOpenSettings();
  const { workspaceId: activeWorkspaceId } = useImbueLocation();
  const dangerColor = useThemeDangerColor();

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedRepos((prev) => ({ ...prev, [group.projectId]: !(prev[group.projectId] ?? false) }));
  };

  const handleRenameCommit = async (workspaceId: string, newName: string): Promise<void> => {
    setRenamingWorkspaceId(null);
    try {
      await updateWorkspace({
        path: { workspace_id: workspaceId },
        body: { description: newName },
      });
    } catch (error) {
      console.error("Failed to rename workspace:", error);
    }
  };

  // JSX and rendering logic
  const isRepoCollapsed = collapsedRepos[group.projectId] ?? false;
  const Chevron = isRepoCollapsed ? ChevronRight : ChevronDown;

  return (
    <div className={styles.repoGroup}>
      <div className={styles.repoHeader}>
        <button
          type="button"
          className={styles.repoHeaderButton}
          onClick={handleToggleCollapsed}
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
            status={statuses.get(ws.objectId) ?? EMPTY_WORKSPACE_DOT_STATUS}
            isRenaming={renamingWorkspaceId === ws.objectId}
            isActive={ws.objectId === activeWorkspaceId}
            actions={actions}
            openInRuntime={openInRuntime}
            destructiveColor={dangerColor}
            onClick={() => onWorkspaceClick(ws.objectId)}
            onHover={() => onWorkspaceHover(ws.objectId)}
            onRenameCommit={(newName) => void handleRenameCommit(ws.objectId, newName)}
            onRenameCancel={() => setRenamingWorkspaceId(null)}
            onBeginDelete={() => onBeginDelete(ws)}
          />
        ))}
    </div>
  );
};
