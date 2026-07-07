// One collapsible repo group in the workspace sidebar: the repo header row (collapse
// chevron, hover-revealed repository settings, and an always-visible "+" that
// direct-creates a workspace in this repo, falling back to the new-workspace dialog
// pre-scoped to the repo when the branch can't be resolved or the create fails),
// followed by one row per workspace while expanded. Cross-group concerns — building
// the groups, the shared action list, and the delete confirmation — stay in
// WorkspaceSidebar and arrive as props; per-group state (collapse, rename) is read
// from its atoms here.
//
// The group is itself a sortable item of WorkspaceSidebar's repo-group DndContext
// (dragged by its header), and it hosts its OWN DndContext for its workspace rows —
// a workspace belongs to its repo, so scoping the row context per group makes
// cross-repo drops structurally impossible rather than merely rejected.

import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import { closestCenter, DndContext, DragOverlay } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ContextMenu, DropdownMenu, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom, useStore } from "jotai";
import { ChevronDown, ChevronRight, MoreHorizontal, Plus, Settings, Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { memo, useCallback, useEffect, useState } from "react";

import type { Workspace } from "~/api";
import { ElementIds, updateWorkspace } from "~/api";
import { useImbueLocation } from "~/common/NavigateUtils.ts";
import { workspaceRenameErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { workspaceAtomFamily, workspaceDotStatusAtomFamily } from "~/common/state/atoms/workspaces.ts";
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
import { useCreateWorkspaceFromSidebar } from "~/components/newWorkspace/useCreateWorkspaceFromSidebar.ts";
import { WorkspaceStatusDots } from "~/components/statusDot";
import { ToastType } from "~/components/Toast.tsx";

import { collapsedRepoGroupsAtom, isRepoCollapsedAtomFamily, isSidebarDragActiveAtom } from "./navAtoms.ts";
import { useSidebarDndSensors } from "./sidebarDnd.ts";
import { WorkspaceRowDragPreview } from "./SidebarDragPreview.tsx";
import styles from "./SidebarRepoGroup.module.scss";
import type { RepoGroup } from "./sidebarWorkspaceOrder.ts";
import { reorderSidebarWorkspaceAtom } from "./sidebarWorkspaceOrder.ts";

/**
 * A single workspace row in the sidebar repo group: the status dot + name (or an
 * inline rename input while renaming), the hover-revealed actions dropdown and
 * delete button, and the wrapping right-click context menu. All behavior is
 * delegated through the callback props.
 *
 * The row owns its status-dot subscription and is memoized: the per-workspace
 * status slice is equality-guarded, so a task streaming tick re-renders only
 * the rows whose aggregate flags actually flip — not the whole sidebar. For
 * the memo to hold, every non-primitive prop must be reference-stable across
 * parent renders (memoized action lists, id-taking callbacks).
 *
 * The row is a sortable item of its group's DndContext: the row div is the measured
 * node, and the name button is the focusable drag activator — the hover action
 * buttons stay outside the listeners so grabbing them can never start a drag.
 */
const SidebarWorkspaceRow = memo(function SidebarWorkspaceRow({
  workspace,
  isRenaming,
  isActive,
  actions,
  openInRuntime,
  destructiveColor,
  onNavigate,
  onHover,
  onRenameCommit,
  onRenameCancel,
  onBeginDelete,
}: {
  workspace: Workspace;
  isRenaming: boolean;
  isActive: boolean;
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
  destructiveColor: ReturnType<typeof useThemeDangerColor>;
  onNavigate: (workspaceId: string) => void;
  onHover: (workspaceId: string) => void;
  onRenameCommit: (workspaceId: string, newName: string) => void;
  onRenameCancel: () => void;
  onBeginDelete: (workspace: Workspace) => void;
}): ReactElement {
  const status = useAtomValue(workspaceDotStatusAtomFamily(workspace.objectId));
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging, isOver } =
    useSortable({
      id: workspace.objectId,
      disabled: isRenaming,
    });

  // Enter navigates from the keyboard, like a click. Space is deliberately NOT
  // handled here: it falls through to the dnd-kit keyboard sensor's activator
  // (listeners.onKeyDown), so the drag pipeline (focus row → Space → arrows →
  // Space) works while Enter can never start a drag. Mid-drag, Enter is the
  // sensor's drop-commit key, so it is left alone rather than navigating out
  // from under the drag.
  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isDragging) {
      event.preventDefault();
      onNavigate(workspace.objectId);
      return;
    }
    listeners?.onKeyDown?.(event);
  };

  const rowClassName = [
    styles.workspaceRow,
    isActive ? styles.workspaceRowActive : "",
    isDragging ? styles.rowDragging : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>
        {/* Translate-only (never CSS.Transform): rows and groups vary in height, and
            the scale component dnd-kit folds into transforms would stretch the
            element toward the hovered slot's size. */}
        <div
          ref={setNodeRef}
          className={rowClassName}
          style={{ transform: CSS.Translate.toString(transform), transition }}
        >
          {isRenaming ? (
            <span className={styles.workspaceRowButton}>
              <span className={styles.workspaceDot}>
                <WorkspaceStatusDots status={status} />
              </span>
              <InlineRenameInput
                value={workspace.description ?? ""}
                onCommit={(newName) => onRenameCommit(workspace.objectId, newName)}
                onCancel={onRenameCancel}
                isEditing={true}
              />
            </span>
          ) : (
            <button
              type="button"
              ref={setActivatorNodeRef}
              className={styles.workspaceRowButton}
              {...attributes}
              {...listeners}
              // After the listeners spread so this composed handler REPLACES the
              // sensor's raw onKeyDown (it delegates every non-Enter key back to it).
              onKeyDown={handleKeyDown}
              onClick={() => onNavigate(workspace.objectId)}
              onMouseEnter={() => onHover(workspace.objectId)}
              data-testid={ElementIds.SIDEBAR_WORKSPACE_ROW}
              data-workspace-id={workspace.objectId}
              data-has-unread={String(status.hasUnread)}
              // Live drag flags for the keyboard-drag pipeline (and its Playwright
              // driver): the dragged row is marked while the drag is active, and the
              // row whose slot the drag currently targets is marked as the drop target.
              data-sidebar-dragging={isDragging ? "true" : undefined}
              data-sidebar-drop-target={isOver && !isDragging ? "true" : undefined}
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
                onClick={() => onBeginDelete(workspace)}
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
});

type SidebarRepoGroupProps = {
  group: RepoGroup;
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
  actions,
  openInRuntime,
  onWorkspaceClick,
  onWorkspaceHover,
  onBeginDelete,
}: SidebarRepoGroupProps): ReactElement => {
  // External atoms
  const isRepoCollapsed = useAtomValue(isRepoCollapsedAtomFamily(group.projectId));
  const setCollapsedRepos = useSetAtom(collapsedRepoGroupsAtom);
  const setRenameErrorToast = useSetAtom(workspaceRenameErrorToastAtom);
  const [renamingWorkspaceId, setRenamingWorkspaceId] = useAtom(renamingWorkspaceIdAtom);
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();
  const setSidebarDragActive = useSetAtom(isSidebarDragActiveAtom);
  const reorderWorkspace = useSetAtom(reorderSidebarWorkspaceAtom);
  const store = useStore();

  // External hooks
  const openSettings = useOpenSettings();
  const { workspaceId: activeWorkspaceId } = useImbueLocation();
  const dangerColor = useThemeDangerColor();

  // The group is a sortable item of WorkspaceSidebar's repo-group context: the
  // whole group (header + rows) is the measured node so its rows travel with it,
  // and the header button is the drag activator.
  const {
    attributes: groupAttributes,
    listeners: groupListeners,
    setNodeRef: setGroupNodeRef,
    setActivatorNodeRef: setGroupActivatorNodeRef,
    transform: groupTransform,
    transition: groupTransition,
    isDragging: isGroupDragging,
    isOver: isGroupOver,
  } = useSortable({ id: group.projectId });

  // The rows' own drag context; see the module comment for why it lives per group.
  const rowDndSensors = useSidebarDndSensors();

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedRepos((prev) => ({ ...prev, [group.projectId]: !(prev[group.projectId] ?? false) }));
  };

  // Enter toggles collapse from the keyboard, like a click; every other key falls
  // through to the dnd-kit keyboard sensor so Space picks the group up (see the
  // matching handler on SidebarWorkspaceRow).
  const handleHeaderKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isGroupDragging) {
      event.preventDefault();
      handleToggleCollapsed();
      return;
    }
    groupListeners?.onKeyDown?.(event);
  };

  // The dragged row's id, so the DragOverlay can render its floating pill copy.
  const [draggedWorkspaceId, setDraggedWorkspaceId] = useState<string | null>(null);
  const handleRowDragStart = useCallback(
    (event: DragStartEvent): void => {
      setDraggedWorkspaceId(String(event.active.id));
      setSidebarDragActive(true);
    },
    [setSidebarDragActive],
  );
  const handleRowDragCancel = useCallback((): void => {
    setDraggedWorkspaceId(null);
    setSidebarDragActive(false);
  }, [setSidebarDragActive]);
  const handleRowDragEnd = useCallback(
    (event: DragEndEvent): void => {
      setDraggedWorkspaceId(null);
      setSidebarDragActive(false);
      if (event.over === null || event.over.id === event.active.id) {
        return;
      }
      reorderWorkspace({
        projectId: group.projectId,
        activeWorkspaceId: String(event.active.id),
        overWorkspaceId: String(event.over.id),
      });
    },
    [setSidebarDragActive, reorderWorkspace, group.projectId],
  );
  const draggedWorkspace = group.workspaces.find((ws) => ws.objectId === draggedWorkspaceId);

  // dnd-kit does not fire onDragCancel when its context unmounts (see
  // PanelDndProvider), and the rows' context unmounts whenever the group
  // collapses — which can happen mid-drag (a keyboard drag is parked while the
  // header stays clickable). Without this reset a stranded drag leaves
  // isSidebarDragActiveAtom stuck true, silently disabling the hover peek.
  useEffect(() => {
    if (isRepoCollapsed) {
      return undefined;
    }
    return handleRowDragCancel;
  }, [isRepoCollapsed, handleRowDragCancel]);

  // Reference-stable (the rows are memoized on their props): the rename
  // callbacks depend only on reference-stable atom setters and the store.
  const handleRenameCommit = useCallback(
    (workspaceId: string, newName: string): void => {
      setRenamingWorkspaceId(null);
      const workspaceAtom = workspaceAtomFamily(workspaceId);
      const previous = store.get(workspaceAtom);
      // Optimistically show the new name and let the WebSocket frame reconcile
      // with the server-authoritative value; roll back and surface a toast if the
      // write is rejected so the rename never fails silently.
      if (previous !== null) {
        store.set(workspaceAtom, { ...previous, description: newName });
      }
      updateWorkspace({
        path: { workspace_id: workspaceId },
        body: { description: newName },
      }).catch((error: unknown) => {
        console.error("Failed to rename workspace:", error);
        if (previous !== null) {
          store.set(workspaceAtom, previous);
        }
        setRenameErrorToast({
          title: `Failed to rename "${previous?.description ?? "workspace"}"`,
          description: "The name has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: null,
        });
      });
    },
    [setRenamingWorkspaceId, setRenameErrorToast, store],
  );

  const handleRenameCancel = useCallback((): void => {
    setRenamingWorkspaceId(null);
  }, [setRenamingWorkspaceId]);

  // JSX and rendering logic
  const Chevron = isRepoCollapsed ? ChevronRight : ChevronDown;

  return (
    <div
      ref={setGroupNodeRef}
      className={`${styles.repoGroup} ${isGroupDragging ? styles.rowDragging : ""}`}
      style={{ transform: CSS.Translate.toString(groupTransform), transition: groupTransition }}
    >
      <div className={styles.repoHeader}>
        <button
          type="button"
          ref={setGroupActivatorNodeRef}
          className={styles.repoHeaderButton}
          {...groupAttributes}
          {...groupListeners}
          // After the listeners spread so this composed handler REPLACES the
          // sensor's raw onKeyDown (it delegates every non-Enter key back to it).
          onKeyDown={handleHeaderKeyDown}
          onClick={handleToggleCollapsed}
          data-testid={ElementIds.SIDEBAR_REPO_GROUP}
          data-project-id={group.projectId}
          data-sidebar-dragging={isGroupDragging ? "true" : undefined}
          data-sidebar-drop-target={isGroupOver && !isGroupDragging ? "true" : undefined}
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
              onClick={() => openSettings("REPOSITORIES", group.projectId)}
              aria-label="Repository settings"
              data-testid={ElementIds.SIDEBAR_REPO_SETTINGS}
              data-project-id={group.projectId}
            >
              <Settings size={13} />
            </IconButton>
          </Tooltip>
          <Tooltip content="New workspace in this repo" side="right">
            {/* Direct-create in THIS repo (fresh auto branch, last-used or
                default settings); failures fall back to the dialog
                pre-selecting the repo. The nav "New Workspace" above is the
                open-the-dialog affordance. */}
            <IconButton
              variant="ghost"
              size="1"
              color="gray"
              disabled={isCreating}
              onClick={() => void createFromSidebar(group.projectId)}
              aria-label="New workspace in this repo"
              data-testid={ElementIds.SIDEBAR_REPO_ADD_WORKSPACE}
              data-project-id={group.projectId}
            >
              <Plus size={13} />
            </IconButton>
          </Tooltip>
        </Flex>
      </div>
      {!isRepoCollapsed && (
        <DndContext
          sensors={rowDndSensors}
          collisionDetection={closestCenter}
          onDragStart={handleRowDragStart}
          onDragEnd={handleRowDragEnd}
          onDragCancel={handleRowDragCancel}
        >
          <SortableContext items={group.workspaces.map((ws) => ws.objectId)} strategy={verticalListSortingStrategy}>
            {group.workspaces.map((ws) => (
              <SidebarWorkspaceRow
                key={ws.objectId}
                workspace={ws}
                isRenaming={renamingWorkspaceId === ws.objectId}
                isActive={ws.objectId === activeWorkspaceId}
                actions={actions}
                openInRuntime={openInRuntime}
                destructiveColor={dangerColor}
                onNavigate={onWorkspaceClick}
                onHover={onWorkspaceHover}
                onRenameCommit={handleRenameCommit}
                onRenameCancel={handleRenameCancel}
                onBeginDelete={onBeginDelete}
              />
            ))}
          </SortableContext>
          {/* The floating row copy that follows the cursor; the source row stays in
              the list, dimmed (mirrors the panel-tab drag overlay). */}
          <DragOverlay dropAnimation={null}>
            {draggedWorkspace !== undefined ? <WorkspaceRowDragPreview workspace={draggedWorkspace} /> : null}
          </DragOverlay>
        </DndContext>
      )}
    </div>
  );
};
