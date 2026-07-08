// A workspace-group card in the sidebar: a rounded, accent-tinted container
// nested inside a repo section, wrapping the group header (chevron + color
// swatch + name + optional CLI chip + hover "⋯" menu) and the member workspace
// rows. The card stamps the group's Radix accent color as `data-accent-color`,
// which remaps the whole `--accent-*` scale for the subtree — the stylesheet
// tints purely through accent tokens and recolors follow a single attribute.
//
// The group menu opens from the hover "⋯" AND from right-click on the header,
// sharing one body across both Radix menu primitives (the same dual-primitive
// pattern as the workspace row menu in contextActions/menu.tsx).

import type { SensorDescriptor, SensorOptions } from "@dnd-kit/core";
import { DndContext } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
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

// Member rows carry sortable hooks from the shared row component, so they need
// a drag context — but with no sensors a drag can never activate inside the
// card (member drag is not part of the group card's interaction set).
const NO_DRAG_SENSORS: Array<SensorDescriptor<SensorOptions>> = [];

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
  // The member rows reuse SidebarWorkspaceRow unchanged, so the card threads
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

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedGroups((prev) => ({ ...prev, [group.objectId]: !(prev[group.objectId] ?? false) }));
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
    // Optimistic retint — the card recolors immediately; a failure rolls the
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
      className={styles.groupCard}
      data-accent-color={group.color}
      data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_CARD}
      data-group-id={group.objectId}
      data-collapsed={isCollapsed ? "true" : undefined}
    >
      <ContextMenu.Root>
        <ContextMenu.Trigger>
          <div className={styles.groupHeader}>
            {isRenaming ? (
              <span className={styles.groupHeaderButton}>
                <Chevron size={15} className={styles.groupChevron} />
                <span className={styles.groupSwatch} />
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
                className={styles.groupHeaderButton}
                onClick={handleToggleCollapsed}
                data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_HEADER}
                data-group-id={group.objectId}
              >
                <Chevron
                  size={15}
                  className={styles.groupChevron}
                  data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_CHEVRON}
                />
                <span className={styles.groupSwatch} />
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
      {!isCollapsed && (
        <div className={styles.groupMembers}>
          <DndContext sensors={NO_DRAG_SENSORS}>
            <SortableContext items={members.map((member) => member.objectId)} strategy={verticalListSortingStrategy}>
              {members.map((member) => (
                <SidebarWorkspaceRow
                  key={member.objectId}
                  workspace={member}
                  isRenaming={renamingWorkspaceId === member.objectId}
                  isActive={member.objectId === activeWorkspaceId}
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
            </SortableContext>
          </DndContext>
        </div>
      )}
    </div>
  );
};
