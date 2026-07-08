import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ContextMenu, DropdownMenu, Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { MoreHorizontal, Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { memo } from "react";

import type { Workspace } from "~/api";
import { ElementIds } from "~/api";
import { workspaceDotStatusAtomFamily } from "~/common/state/atoms/workspaces.ts";
import type { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import {
  type OpenInRuntime,
  WorkspaceContextMenuContent,
  WorkspaceDropdownMenuContent,
} from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceAction } from "~/components/CommandPalette/contextActions/types.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { WorkspaceStatusDots } from "~/components/statusDot";

// The row is styled by the repo section's shared stylesheet: its classes are
// selector-coupled to the section chrome (hover-reveal and drag-suppression
// rules key on .workspaceRow), so the row reads the same module rather than
// duplicating those rules.
import styles from "./SidebarRepoGroup.module.scss";

/**
 * A single workspace row in the sidebar: the status dot + name (or an inline
 * rename input while renaming), the hover-revealed actions dropdown and delete
 * button, and the wrapping right-click context menu. All behavior is delegated
 * through the callback props. Rendered both as a loose row directly under a
 * repo header and as a member row inside a workspace-group card.
 *
 * The row owns its status-dot subscription and is memoized: the per-workspace
 * status slice is equality-guarded, so a task streaming tick re-renders only
 * the rows whose aggregate flags actually flip — not the whole sidebar. For
 * the memo to hold, every non-primitive prop must be reference-stable across
 * parent renders (memoized action lists, id-taking callbacks).
 *
 * The row is a sortable item of its list's DndContext: the row div is the measured
 * node, and the name button is the focusable drag activator — the hover action
 * buttons stay outside the listeners so grabbing them can never start a drag.
 */
export const SidebarWorkspaceRow = memo(function SidebarWorkspaceRow({
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
