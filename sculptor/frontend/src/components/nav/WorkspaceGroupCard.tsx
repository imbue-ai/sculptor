// A workspace-group card in the sidebar: a rounded, accent-tinted container
// nested inside a repo section, wrapping the group header (chevron + color
// swatch + name + optional CLI chip + hover "⋯" menu) and the member workspace
// rows. The card stamps the group's Radix accent color as `data-accent-color`,
// which remaps the whole `--accent-*` scale for the subtree — the stylesheet
// tints purely through accent tokens and recolors follow a single attribute.
//
// The card is one sortable child of its repo section's mixed lane (dragged by
// its header, like a repo group; a collapsed card is just its header), and it
// is a drop TARGET for workspace rows from outside the group: while such a
// drag is in flight the member box grows a dashed drop slot, and whenever the
// drag hovers the card (the card body, a member row, or the slot) the card
// lights up with an accent ring and a stronger tint. Member rows join the same
// DndContext through the card's nested SortableContext, so they reorder within
// the card and travel out of it.
//
// The group menu opens from the hover "⋯" AND from right-click on the header,
// sharing one body across both Radix menu primitives (the same dual-primitive
// pattern as the workspace row menu in contextActions/menu.tsx).

import { useDndContext, useDroppable } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
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
import type { SidebarGroupCardDragData } from "./sidebarDnd.ts";
import { getSidebarDragData, workspaceGroupDropSlotId } from "./sidebarDnd.ts";
import { SidebarWorkspaceRow } from "./SidebarWorkspaceRow.tsx";
import styles from "./WorkspaceGroupCard.module.scss";

/**
 * The dashed "Drop to add to group" slot at the end of the member rows. It is a
 * plain droppable (not a sortable child): dropping on it appends the dragged
 * workspace to the group. It mounts for the whole lifetime of an eligible drag
 * rather than only while the card is hovered, so the card's geometry stays
 * stable mid-drag (dnd-kit re-measures every droppable when the slot registers
 * at drag start — a slot that popped in and out under the pointer would churn
 * those rects and flicker the drop resolution).
 */
const WorkspaceGroupDropSlot = ({ groupId }: { groupId: string }): ReactElement => {
  const { setNodeRef } = useDroppable({
    id: workspaceGroupDropSlotId(groupId),
    data: { sidebarKind: "workspace-group-drop-slot", groupId },
  });
  return (
    <div
      ref={setNodeRef}
      className={styles.dropSlot}
      data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_DROP_SLOT}
      data-group-id={groupId}
    >
      Drop to add to group
    </div>
  );
};

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

  // The card is a sortable child of the repo section's mixed lane: the whole
  // card (header + member rows) is the measured node so its members travel
  // with it, and the header button is the drag activator — a collapsed card is
  // just its header, so it drags as one.
  const cardDragData: SidebarGroupCardDragData = { sidebarKind: "workspace-group" };
  const {
    attributes: cardAttributes,
    listeners: cardListeners,
    setNodeRef: setCardNodeRef,
    setActivatorNodeRef: setCardActivatorNodeRef,
    transform: cardTransform,
    transition: cardTransition,
    isDragging: isCardDragging,
    isOver: isCardOver,
  } = useSortable({ id: group.objectId, disabled: isRenaming, data: cardDragData });

  // Membership drop-target state: a workspace row from OUTSIDE this group is in
  // flight, and this card is lit while that drag hovers any part of it (the card
  // body, a member row, or the drop slot). While such a drag is in flight the
  // drop slot mounts (see WorkspaceGroupDropSlot for why it stays mounted for
  // the whole drag).
  const { active: dndActive, over: dndOver } = useDndContext();
  const activeDragData = getSidebarDragData(dndActive);
  const isEligibleRowDragActive =
    activeDragData?.sidebarKind === "workspace" && activeDragData.containerId !== group.objectId;
  const overId = dndOver === null ? null : String(dndOver.id);
  const isMembershipDropActive =
    isEligibleRowDragActive &&
    overId !== null &&
    (overId === group.objectId ||
      overId === workspaceGroupDropSlotId(group.objectId) ||
      members.some((member) => member.objectId === overId));

  // Functions and callbacks
  const handleToggleCollapsed = (): void => {
    setCollapsedGroups((prev) => ({ ...prev, [group.objectId]: !(prev[group.objectId] ?? false) }));
  };

  // Enter toggles collapse from the keyboard, like a click; every other key
  // falls through to the dnd-kit keyboard sensor so Space picks the card up
  // (see the matching handler on the repo header in SidebarRepoGroup).
  const handleHeaderKeyDown = (event: React.KeyboardEvent<HTMLElement>): void => {
    if (event.key === "Enter" && event.target === event.currentTarget && !isCardDragging) {
      event.preventDefault();
      handleToggleCollapsed();
      return;
    }
    cardListeners?.onKeyDown?.(event);
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
    // Translate-only (never CSS.Transform): the mixed lane's children vary in
    // height, and the scale component dnd-kit folds into transforms would
    // stretch the card toward the hovered slot's size.
    <div
      ref={setCardNodeRef}
      className={`${styles.groupCard} ${isCardDragging ? styles.cardDragging : ""} ${isMembershipDropActive ? styles.dropActive : ""}`}
      style={{ transform: CSS.Translate.toString(cardTransform), transition: cardTransition }}
      data-accent-color={group.color}
      data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_CARD}
      data-group-id={group.objectId}
      data-collapsed={isCollapsed ? "true" : undefined}
      data-drop-active={isMembershipDropActive ? "true" : undefined}
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
                ref={setCardActivatorNodeRef}
                className={styles.groupHeaderButton}
                {...cardAttributes}
                {...cardListeners}
                // After the listeners spread so this composed handler REPLACES the
                // sensor's raw onKeyDown (it delegates every non-Enter key back to it).
                onKeyDown={handleHeaderKeyDown}
                onClick={handleToggleCollapsed}
                data-testid={ElementIds.SIDEBAR_WORKSPACE_GROUP_HEADER}
                data-group-id={group.objectId}
                data-sidebar-dragging={isCardDragging ? "true" : undefined}
                data-sidebar-drop-target={isCardOver && !isCardDragging ? "true" : undefined}
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
          {/* The nearest SortableContext wins, so the member rows sort against
              each other (not the mixed lane) while still registering with the
              repo section's DndContext — which is what lets a member travel out
              of the card and a foreign row land inside it. */}
          <SortableContext items={members.map((member) => member.objectId)} strategy={verticalListSortingStrategy}>
            {members.map((member) => (
              <SidebarWorkspaceRow
                key={member.objectId}
                workspace={member}
                isRenaming={renamingWorkspaceId === member.objectId}
                isActive={member.objectId === activeWorkspaceId}
                dndContainerId={group.objectId}
                dndAccentColor={group.color}
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
          {isEligibleRowDragActive && <WorkspaceGroupDropSlot groupId={group.objectId} />}
        </div>
      )}
    </div>
  );
};
