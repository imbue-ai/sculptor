// A workspace-group run in the sidebar, Dia-style (REQ-UI-1): an always-
// visible rounded accent-tinted box wrapping the header row (chevron +
// accent-colored name + optional CLI chip + hover "⋯" menu) and the member
// workspace rows indented beneath it. The box shows one shade stronger on
// hover, and — because it is real layout, not a drag transform — it
// physically wraps the mid-drag drop gap, which is what makes "inside vs
// outside" read unambiguously (REQ-DND-6). The wrapper stamps the group's
// Radix accent color as `data-accent-color`, remapping the `--accent-*` scale
// for the subtree, so recolors follow a single attribute.
//
// The run is NOT one sortable unit in the DOM: the header row and each member
// row register individually with the repo section's single flat
// SortableContext (SidebarRepoGroup), and membership is derived from position
// by the section's drop projection. Dragging the header moves the whole group
// (REQ-DND-4): its members collapse into the drag (they unmount, leaving the
// header's slot as the gap) and the section's DragOverlay shows the full run.
//
// The group menu opens from the hover "⋯" AND from right-click on the header,
// sharing one body across both Radix menu primitives (the same dual-primitive
// pattern as the workspace row menu in contextActions/menu.tsx).

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ContextMenu, DropdownMenu, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { ChevronDown, ChevronRight, MoreHorizontal } from "lucide-react";
import type { ComponentType, ReactElement, ReactNode } from "react";
import { useState } from "react";

import type { Workspace, WorkspaceGroup } from "~/api";
import { ElementIds, WorkspaceGroupColor } from "~/api";
import { workspaceGroupErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import type { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import {
  useAddWorkspaceGroupMemberMutation,
  useUngroupWorkspaceGroupMutation,
  useUpdateWorkspaceGroupMutation,
} from "~/common/state/mutations/workspaceGroups.ts";
import type { OpenInRuntime } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { WorkspaceAction } from "~/components/CommandPalette/contextActions/types.ts";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { useCreateWorkspaceFromSidebar } from "~/components/newWorkspace/useCreateWorkspaceFromSidebar.ts";
import { ToastType } from "~/components/Toast.tsx";

import { collapsedWorkspaceGroupsAtom, isWorkspaceGroupCollapsedAtomFamily } from "./navAtoms.ts";
import { SidebarWorkspaceRow } from "./SidebarWorkspaceRow.tsx";
import styles from "./WorkspaceGroupCard.module.scss";

/**
 * The Radix menu primitives the group menu body renders through. As with the
 * workspace row menu, `ContextMenu.*` and `DropdownMenu.*` expose the same
 * sub-API, so one body renders into both the right-click menu and the header's
 * "⋯" dropdown without maintaining two divergent lists.
 */
type GroupMenuComponents = {
  Item: ComponentType<{
    "aria-label"?: string;
    "data-accent-color"?: string;
    "data-color"?: string;
    "data-group-id"?: string;
    "data-testid"?: string;
    className?: string;
    disabled?: boolean;
    onSelect?: (event: Event) => void;
    children?: ReactNode;
  }>;
  Separator: ComponentType;
  Label: ComponentType<{ children?: ReactNode }>;
};

const CONTEXT_MENU_COMPONENTS: GroupMenuComponents = {
  Item: ContextMenu.Item as GroupMenuComponents["Item"],
  Separator: ContextMenu.Separator as GroupMenuComponents["Separator"],
  Label: ContextMenu.Label as GroupMenuComponents["Label"],
};

const DROPDOWN_MENU_COMPONENTS: GroupMenuComponents = {
  Item: DropdownMenu.Item as GroupMenuComponents["Item"],
  Separator: DropdownMenu.Separator as GroupMenuComponents["Separator"],
  Label: DropdownMenu.Label as GroupMenuComponents["Label"],
};

/**
 * The group menu body (REQ-MENU-1): text-only items — New workspace in group,
 * Rename…, Collapse/Expand group, the color-swatch row, Ungroup. No delete:
 * a group is only a container, so Ungroup is the strongest action it offers.
 */
const WorkspaceGroupMenuItems = ({
  menu,
  group,
  isCollapsed,
  isCreateDisabled,
  onNewWorkspaceInGroup,
  onBeginRename,
  onToggleCollapsed,
  onSelectColor,
  onUngroup,
}: {
  menu: GroupMenuComponents;
  group: WorkspaceGroup;
  isCollapsed: boolean;
  isCreateDisabled: boolean;
  onNewWorkspaceInGroup: () => void;
  onBeginRename: () => void;
  onToggleCollapsed: () => void;
  onSelectColor: (color: WorkspaceGroupColor) => void;
  onUngroup: () => void;
}): ReactElement => (
  <>
    <menu.Item
      data-testid={ElementIds.WORKSPACE_GROUP_MENU_NEW_WORKSPACE}
      data-group-id={group.objectId}
      disabled={isCreateDisabled}
      onSelect={onNewWorkspaceInGroup}
    >
      New workspace in group
    </menu.Item>
    <menu.Item
      data-testid={ElementIds.WORKSPACE_GROUP_MENU_RENAME}
      data-group-id={group.objectId}
      onSelect={onBeginRename}
    >
      Rename…
    </menu.Item>
    <menu.Item
      data-testid={ElementIds.WORKSPACE_GROUP_MENU_COLLAPSE}
      data-group-id={group.objectId}
      onSelect={onToggleCollapsed}
    >
      {isCollapsed ? "Expand group" : "Collapse group"}
    </menu.Item>
    <menu.Separator />
    <menu.Label>Color</menu.Label>
    <div className={styles.swatchRow} data-testid={ElementIds.WORKSPACE_GROUP_MENU_SWATCH_ROW}>
      {/* The swatches iterate the generated palette constant — the server
          cycles the same enum when auto-assigning colors, so the row can
          never drift from the palette. */}
      {Object.values(WorkspaceGroupColor).map((color) => (
        <menu.Item
          key={color}
          className={`${styles.menuSwatch} ${color === group.color ? styles.menuSwatchSelected : ""}`}
          aria-label={`Set group color to ${color}`}
          data-testid={ElementIds.WORKSPACE_GROUP_MENU_SWATCH}
          data-accent-color={color}
          data-color={color}
          data-group-id={group.objectId}
          onSelect={() => onSelectColor(color)}
        />
      ))}
    </div>
    <menu.Separator />
    <menu.Item
      data-testid={ElementIds.WORKSPACE_GROUP_MENU_UNGROUP}
      data-group-id={group.objectId}
      onSelect={onUngroup}
    >
      Ungroup
    </menu.Item>
  </>
);

type WorkspaceGroupCardProps = {
  group: WorkspaceGroup;
  /** The group's member workspaces, already in render order. */
  members: ReadonlyArray<Workspace>;
  /**
   * The section's active drag projects its drop inside this group, so the
   * container surface lights up and wraps the gap (REQ-DND-1/6). Also set
   * while a drag hovers a collapsed run's header (the append case).
   */
  isProjectedTarget: boolean;
  // The member rows reuse SidebarWorkspaceRow unchanged, so the run threads
  // through the same row plumbing SidebarRepoGroup passes its loose rows.
  actions: ReadonlyArray<WorkspaceAction>;
  openInRuntime: OpenInRuntime;
  destructiveColor: ReturnType<typeof useThemeDangerColor>;
  renamingWorkspaceId: string | null;
  // Null (not undefined) to match useImbueLocation's "no active workspace".
  activeWorkspaceId: string | null;
  onWorkspaceClick: (workspaceId: string) => void;
  onWorkspaceHover: (workspaceId: string) => void;
  onWorkspaceRenameCommit: (workspaceId: string, newName: string) => void;
  onWorkspaceRenameCancel: () => void;
  onBeginDelete: (workspace: Workspace) => void;
};

export const WorkspaceGroupCard = ({
  group,
  members,
  isProjectedTarget,
  actions,
  openInRuntime,
  destructiveColor,
  renamingWorkspaceId,
  activeWorkspaceId,
  onWorkspaceClick,
  onWorkspaceHover,
  onWorkspaceRenameCommit,
  onWorkspaceRenameCancel,
  onBeginDelete,
}: WorkspaceGroupCardProps): ReactElement => {
  // External atoms
  const isCollapsed = useAtomValue(isWorkspaceGroupCollapsedAtomFamily(group.objectId));
  const setCollapsedGroups = useSetAtom(collapsedWorkspaceGroupsAtom);
  const setGroupErrorToast = useSetAtom(workspaceGroupErrorToastAtom);

  // Internal state
  const [isRenaming, setIsRenaming] = useState<boolean>(false);

  // External hooks
  const updateGroup = useUpdateWorkspaceGroupMutation();
  const ungroupGroup = useUngroupWorkspaceGroupMutation();
  const addMember = useAddWorkspaceGroupMemberMutation();
  const { createFromSidebar, isCreating } = useCreateWorkspaceFromSidebar();

  // The header row is the group's sortable item in the section's flat lane
  // (the members register individually). While the header is dragged the
  // members unmount below, so the header's in-flow placeholder is the whole
  // gap and the run travels as one unit in the overlay (REQ-DND-4).
  const {
    attributes: headerAttributes,
    listeners: headerListeners,
    setNodeRef: setHeaderNodeRef,
    setActivatorNodeRef: setHeaderActivatorNodeRef,
    transform: headerTransform,
    transition: headerTransition,
    isDragging: isGroupDragging,
    isOver: isHeaderOver,
  } = useSortable({ id: group.objectId, disabled: isRenaming });

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedGroups((prev) => ({ ...prev, [group.objectId]: !(prev[group.objectId] ?? false) }));
  };

  // Enter toggles collapse from the keyboard, like a click; every other key
  // falls through to the dnd-kit keyboard sensor so Space picks the group up
  // (see the matching handler on the repo header in SidebarRepoGroup).
  const handleHeaderKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isGroupDragging) {
      event.preventDefault();
      handleToggleCollapsed();
      return;
    }
    headerListeners?.onKeyDown?.(event);
  };

  const handleRenameCommit = (newName: string): void => {
    setIsRenaming(false);
    // Optimistic (the mutation snapshots and rolls back on failure); the toast
    // is the only signal the write didn't stick.
    updateGroup.mutate(
      { groupId: group.objectId, name: newName },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: `Failed to rename "${group.name}"`,
            description: "The name has been restored. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  const handleSelectColor = (color: WorkspaceGroupColor): void => {
    if (color === group.color) {
      return;
    }
    // Optimistic retint — the run recolors immediately; a failure rolls the
    // color back, so the toast is the only signal it didn't stick.
    updateGroup.mutate(
      { groupId: group.objectId, color },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: `Failed to recolor "${group.name}"`,
            description: "The color has been restored. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  const handleUngroup = (): void => {
    ungroupGroup.mutate(
      { groupId: group.objectId },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: `Failed to ungroup "${group.name}"`,
            description: "The group is unchanged. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  // The repo's normal direct-create flow, then the new workspace joins this
  // group. A null id means the create fell back to the new-workspace dialog
  // (or failed, which the create flow already toasts): the dialog flow has no
  // group context, so a workspace created through it stays loose.
  const handleNewWorkspaceInGroup = async (): Promise<void> => {
    const workspaceId = await createFromSidebar(group.projectId);
    if (workspaceId === null) {
      return;
    }
    addMember.mutate(
      { groupId: group.objectId, workspaceId },
      {
        onError: (): void => {
          setGroupErrorToast({
            title: `Failed to add the new workspace to "${group.name}"`,
            description: "The workspace was created outside the group. Add it from its context menu.",
            type: ToastType.ERROR_PROMINENT,
            action: null,
          });
        },
      },
    );
  };

  // JSX and rendering logic
  const Chevron = isCollapsed ? ChevronRight : ChevronDown;
  const menuItemProps = {
    group,
    isCollapsed,
    isCreateDisabled: isCreating,
    onNewWorkspaceInGroup: (): void => void handleNewWorkspaceInGroup(),
    onBeginRename: (): void => setIsRenaming(true),
    onToggleCollapsed: handleToggleCollapsed,
    onSelectColor: handleSelectColor,
    onUngroup: handleUngroup,
  };

  return (
    <div
      className={`${styles.groupCard} ${isGroupDragging ? styles.cardDragging : ""} ${isProjectedTarget ? styles.dropActive : ""}`}
      data-accent-color={group.color}
      data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_CARD}
      data-group-id={group.objectId}
      data-collapsed={isCollapsed ? "true" : undefined}
      data-drop-active={isProjectedTarget ? "true" : undefined}
    >
      <ContextMenu.Root>
        <ContextMenu.Trigger>
          {/* Translate-only (never CSS.Transform): the lane's rows vary in
              height, and the scale component dnd-kit folds into transforms
              would stretch the header toward the hovered slot's size. */}
          <div
            ref={setHeaderNodeRef}
            className={styles.groupHeader}
            style={{ transform: CSS.Translate.toString(headerTransform), transition: headerTransition }}
          >
            {isRenaming ? (
              <span className={styles.groupHeaderButton}>
                <Chevron size={15} className={styles.groupChevron} />
                <InlineRenameInput
                  value={group.name}
                  onCommit={handleRenameCommit}
                  onCancel={() => setIsRenaming(false)}
                  isEditing={true}
                />
              </span>
            ) : (
              <button
                type="button"
                ref={setHeaderActivatorNodeRef}
                className={styles.groupHeaderButton}
                {...headerAttributes}
                {...headerListeners}
                // After the listeners spread so this composed handler REPLACES the
                // sensor's raw onKeyDown (it delegates every non-Enter key back to it).
                onKeyDown={handleHeaderKeyDown}
                onClick={handleToggleCollapsed}
                data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_HEADER}
                data-group-id={group.objectId}
                data-sidebar-dragging={isGroupDragging ? "true" : undefined}
                data-sidebar-drop-target={isHeaderOver && !isGroupDragging ? "true" : undefined}
              >
                <Chevron
                  size={15}
                  className={styles.groupChevron}
                  data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_CHEVRON}
                />
                <Text className={styles.groupName} truncate>
                  {group.name}
                </Text>
                {group.createdViaCli === true && (
                  <span className={styles.cliBadge} data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_CLI_BADGE}>
                    CLI
                  </span>
                )}
              </button>
            )}
            <Flex className={`${styles.rowActions} ${styles.hoverReveal}`} gap="2">
              <DropdownMenu.Root>
                <Tooltip content="Group actions" side="bottom">
                  <DropdownMenu.Trigger>
                    <IconButton
                      variant="ghost"
                      size="1"
                      color="gray"
                      aria-label="Group actions"
                      data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_MENU_TRIGGER}
                      data-group-id={group.objectId}
                    >
                      <MoreHorizontal size={13} />
                    </IconButton>
                  </DropdownMenu.Trigger>
                </Tooltip>
                {/* Rename mounts a focus-stealing input on menu close, so the
                    close-time focus restore is suppressed (see InlineRenameInput). */}
                <DropdownMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
                  <WorkspaceGroupMenuItems menu={DROPDOWN_MENU_COMPONENTS} {...menuItemProps} />
                </DropdownMenu.Content>
              </DropdownMenu.Root>
            </Flex>
          </div>
        </ContextMenu.Trigger>
        <ContextMenu.Content size="1" onCloseAutoFocus={(e): void => e.preventDefault()}>
          <WorkspaceGroupMenuItems menu={CONTEXT_MENU_COMPONENTS} {...menuItemProps} />
        </ContextMenu.Content>
      </ContextMenu.Root>
      {!isCollapsed && !isGroupDragging && members.length > 0 && (
        <div className={styles.groupMembers}>
          {members.map((member) => (
            <SidebarWorkspaceRow
              key={member.objectId}
              workspace={member}
              isRenaming={renamingWorkspaceId === member.objectId}
              isActive={member.objectId === activeWorkspaceId}
              isGroupMember
              actions={actions}
              openInRuntime={openInRuntime}
              destructiveColor={destructiveColor}
              onNavigate={onWorkspaceClick}
              onHover={onWorkspaceHover}
              onRenameCommit={onWorkspaceRenameCommit}
              onRenameCancel={onWorkspaceRenameCancel}
              onBeginDelete={onBeginDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
};
