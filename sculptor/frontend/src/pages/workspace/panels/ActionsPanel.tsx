import type { DragEndEvent, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, DragOverlay, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useDraggable } from "@dnd-kit/core";
import { Badge, Button, ContextMenu, Flex, Text, TextField } from "@radix-ui/themes";
import { useAtom, useAtomValue } from "jotai";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import type { ReactElement } from "react";
import { useRef, useState } from "react";

import type { CustomAction, CustomActionGroup } from "~/api";
import { ElementIds } from "~/api";
import {
  BUILTIN_SCULPTOR_ACTIONS,
  BUILTIN_SCULPTOR_GROUP,
  isBuiltInAction,
  isBuiltInGroup,
  SCULPTOR_BUILTIN_GROUP_ID,
} from "~/common/builtinActions";
import { chatActionsAtom } from "~/common/state/atoms/chatActions";
import { collapsedGroupsAtom } from "~/common/state/atoms/customActions";
import { useCustomActions } from "~/common/state/hooks/useCustomActions";
import { ActionChip } from "~/components/actions/ActionChip";
import { ActionDialog, type ActionFormData } from "~/components/actions/ActionDialog";
import { DeleteActionDialog } from "~/components/actions/DeleteActionDialog";
import { DeleteGroupDialog } from "~/components/actions/DeleteGroupDialog";
import { GroupContextMenu } from "~/components/actions/GroupContextMenu";
import { PanelHeader } from "~/components/panels/PanelHeader";
import { registerPanelComponent } from "~/components/sections/registry/panelRegistry.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";

import styles from "./ActionsPanel.module.scss";
import { useWorkspacePanelData } from "./useWorkspacePanelData";

type DropTargetInfo = {
  id: string;
  type: "action" | "empty-group" | "group";
  position: "before" | "after";
  groupId: string | null;
};

type DraggableActionChipProps = {
  action: CustomAction;
  onClick: () => void;
  disabled: boolean;
  groups: ReadonlyArray<CustomActionGroup>;
  onEdit: (action: CustomAction) => void;
  onDelete: (action: CustomAction) => void;
  onMoveToGroup: (action: CustomAction, groupId: string | null) => void;
  isAgentRunning: boolean;
  onQueueMessage: (prompt: string) => void;
  dropPosition?: "before" | "after";
  isDragSource?: boolean;
};

const DraggableActionChip = ({
  action,
  onClick,
  disabled,
  groups,
  onEdit,
  onDelete,
  onMoveToGroup,
  isAgentRunning,
  onQueueMessage,
  dropPosition,
  isDragSource,
}: DraggableActionChipProps): ReactElement => {
  const isBuiltIn = isBuiltInAction(action.id);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: action.id,
    data: { type: "action", groupId: action.groupId ?? null },
    disabled: isBuiltIn,
  });

  const wrapperClassName = [
    styles.chipWrapper,
    dropPosition === "before" ? styles.dropBefore : "",
    dropPosition === "after" ? styles.dropAfter : "",
    isDragging || isDragSource ? styles.chipDragging : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Built-in chips are not draggable and don't expose an edit/delete/move context menu.
  // Omit data-action-chip so they're not considered as drop targets.
  return (
    <div
      ref={setNodeRef}
      className={wrapperClassName}
      {...(isBuiltIn ? {} : { "data-action-chip": action.id })}
      {...(isBuiltIn ? {} : attributes)}
      {...(isBuiltIn ? {} : listeners)}
    >
      <ActionChip
        action={action}
        onClick={onClick}
        disabled={disabled}
        groups={groups}
        onEdit={isBuiltIn ? undefined : onEdit}
        onDelete={isBuiltIn ? undefined : onDelete}
        onMoveToGroup={isBuiltIn ? undefined : onMoveToGroup}
        isAgentRunning={isAgentRunning}
        onQueueMessage={onQueueMessage}
        isDragging={isDragging || isDragSource}
      />
    </div>
  );
};

type DraggableGroupHeaderProps = {
  group: CustomActionGroup;
  actionCount: number;
  isCollapsed: boolean;
  isRenaming: boolean;
  renamingGroupName: string;
  onRenamingGroupNameChange: (name: string) => void;
  onRenameSubmit: () => void;
  onRenameCancel: () => void;
  onToggleCollapse: () => void;
  onRename: (group: CustomActionGroup) => void;
  onDelete: (group: CustomActionGroup) => void;
  dropPosition?: "before" | "after";
  isDragSource?: boolean;
};

const DraggableGroupHeader = ({
  group,
  actionCount,
  isCollapsed,
  isRenaming,
  renamingGroupName,
  onRenamingGroupNameChange,
  onRenameSubmit,
  onRenameCancel,
  onToggleCollapse,
  onRename,
  onDelete,
  dropPosition,
  isDragSource,
}: DraggableGroupHeaderProps): ReactElement => {
  const isBuiltIn = isBuiltInGroup(group.id);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `group:${group.id}`,
    data: { type: "group" },
    disabled: isBuiltIn,
  });

  const wrapperClassName = [
    styles.groupHeaderWrapper,
    dropPosition === "before" ? styles.groupDropBefore : "",
    dropPosition === "after" ? styles.groupDropAfter : "",
    isDragging || isDragSource ? styles.groupDragging : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Built-in groups are not draggable, omit data-group-header so they're skipped in reorder targeting,
  // and don't wrap the header in GroupContextMenu (no rename / delete).
  const headerContent = (
    <Flex
      className={styles.groupHeader}
      align="center"
      gap="2"
      onClick={() => {
        if (!isRenaming) {
          onToggleCollapse();
        }
      }}
    >
      {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
      {isRenaming ? (
        <TextField.Root
          size="1"
          value={renamingGroupName}
          onChange={(e) => onRenamingGroupNameChange(e.target.value)}
          onBlur={onRenameSubmit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onRenameSubmit();
            } else if (e.key === "Escape") {
              onRenameCancel();
            }
          }}
          onClick={(e) => e.stopPropagation()}
          autoFocus
          className={styles.renameField}
        />
      ) : (
        <Text size="1" className={styles.groupName} weight="medium" color="gray">
          {group.name}
        </Text>
      )}
      {isCollapsed && actionCount > 0 && !isRenaming && (
        <Badge className={styles.countBadge} size="1" color="gray" variant="soft">
          {actionCount}
        </Badge>
      )}
    </Flex>
  );

  return (
    <div
      ref={setNodeRef}
      className={wrapperClassName}
      {...(isBuiltIn ? {} : { "data-group-header": group.id })}
      data-testid={ElementIds.ACTIONS_PANEL_GROUP_HEADER}
      {...(isBuiltIn ? {} : attributes)}
      {...(isBuiltIn ? {} : listeners)}
    >
      {isBuiltIn ? (
        headerContent
      ) : (
        <GroupContextMenu group={group} onRename={onRename} onDelete={onDelete}>
          {headerContent}
        </GroupContextMenu>
      )}
    </div>
  );
};

export const ActionsPanel = (): ReactElement => {
  const {
    actions,
    groups,
    addAction,
    addActionWithNewGroup,
    addGroup,
    updateAction,
    updateActionWithNewGroup,
    deleteAction,
    moveActionToGroup,
    reorderActions,
    reorderGroups,
    renameGroup,
    deleteGroup,
    getActionsInGroup,
    getUngroupedActions,
    getSortedGroups,
  } = useCustomActions();
  const [collapsedGroups, setCollapsedGroups] = useAtom(collapsedGroupsAtom);
  const chatActions = useAtomValue(chatActionsAtom);
  const { task } = useWorkspacePanelData();

  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingAction, setEditingAction] = useState<CustomAction | undefined>(undefined);
  const [creatingGroupName, setCreatingGroupName] = useState<string | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [actionToDelete, setActionToDelete] = useState<CustomAction | null>(null);
  const [isDeleteGroupDialogOpen, setIsDeleteGroupDialogOpen] = useState(false);
  const [groupToDelete, setGroupToDelete] = useState<CustomActionGroup | null>(null);
  const [renamingGroupId, setRenamingGroupId] = useState<string | null>(null);
  const [renamingGroupName, setRenamingGroupName] = useState("");

  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTargetInfo | null>(null);
  const dropTargetRef = useRef<DropTargetInfo | null>(null);
  const pendingGroupCreateRef = useRef(false);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleContextMenuCloseAutoFocus = (event: Event): void => {
    // When "Add group" was selected, prevent Radix from restoring focus to the trigger.
    // This allows the autoFocus on the group name TextField to work correctly.
    if (pendingGroupCreateRef.current) {
      event.preventDefault();
      pendingGroupCreateRef.current = false;
    }
  };

  const ungroupedActions = getUngroupedActions();
  // The built-in Sculptor group is injected virtually at the display boundary and always
  // renders first. User groups keep their own ordering.
  const sortedGroups: ReadonlyArray<CustomActionGroup> = [BUILTIN_SCULPTOR_GROUP, ...getSortedGroups()];
  const getDisplayActionsInGroup = (groupId: string): ReadonlyArray<CustomAction> => {
    if (groupId === SCULPTOR_BUILTIN_GROUP_ID) return BUILTIN_SCULPTOR_ACTIONS;
    return getActionsInGroup(groupId);
  };

  const isAgentRunning = task?.status === "RUNNING" || task?.status === "BUILDING";

  const handleAddAction = (): void => {
    setEditingAction(undefined);
    setIsDialogOpen(true);
  };

  const handleAddGroup = (): void => {
    pendingGroupCreateRef.current = true;
    setCreatingGroupName("");
  };

  const handleSaveAction = async (formData: ActionFormData): Promise<void> => {
    if (editingAction) {
      if (formData.newGroupName) {
        await updateActionWithNewGroup(
          { ...editingAction, name: formData.name, prompt: formData.prompt, autoSubmit: formData.autoSubmit },
          formData.newGroupName,
        );
      } else {
        await updateAction({
          ...editingAction,
          name: formData.name,
          prompt: formData.prompt,
          autoSubmit: formData.autoSubmit,
          groupId: formData.groupId,
        });
      }
    } else if (formData.newGroupName) {
      await addActionWithNewGroup(
        { name: formData.name, prompt: formData.prompt, autoSubmit: formData.autoSubmit },
        formData.newGroupName,
      );
    } else {
      await addAction({
        name: formData.name,
        prompt: formData.prompt,
        autoSubmit: formData.autoSubmit,
        groupId: formData.groupId,
      });
    }

    setIsDialogOpen(false);
  };

  const handleActionClick = (action: CustomAction): void => {
    const isAutoSubmit = action.autoSubmit ?? true;
    if (isAutoSubmit) {
      chatActions.sendMessage?.(action.prompt);
    } else {
      chatActions.appendText?.(action.prompt);
    }
  };

  const handleEditAction = (action: CustomAction): void => {
    setEditingAction(action);
    setIsDialogOpen(true);
  };

  const handleDeleteAction = (action: CustomAction): void => {
    setActionToDelete(action);
    setIsDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async (): Promise<void> => {
    if (actionToDelete) {
      await deleteAction(actionToDelete.id);
      setActionToDelete(null);
      setIsDeleteDialogOpen(false);
    }
  };

  const handleMoveToGroup = async (action: CustomAction, groupId: string | null): Promise<void> => {
    await moveActionToGroup(action.id, groupId);
  };

  const handleQueueMessage = (prompt: string): void => {
    chatActions.sendMessage?.(prompt);
  };

  const handleCreateGroup = async (): Promise<void> => {
    if (creatingGroupName && creatingGroupName.trim() !== "") {
      await addGroup(creatingGroupName.trim());
      setCreatingGroupName(null);
    }
  };

  const handleCancelCreateGroup = (): void => {
    setCreatingGroupName(null);
  };

  const toggleGroupCollapse = (groupId: string): void => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
  };

  const handleRenameGroup = (group: CustomActionGroup): void => {
    setRenamingGroupId(group.id);
    setRenamingGroupName(group.name);
  };

  const handleRenameGroupSubmit = async (): Promise<void> => {
    if (renamingGroupId && renamingGroupName.trim()) {
      await renameGroup(renamingGroupId, renamingGroupName.trim());
    }
    setRenamingGroupId(null);
  };

  const handleRenameGroupCancel = (): void => {
    setRenamingGroupId(null);
  };

  const handleDeleteGroup = (group: CustomActionGroup): void => {
    setGroupToDelete(group);
    setIsDeleteGroupDialogOpen(true);
  };

  const handleConfirmDeleteGroup = async (): Promise<void> => {
    if (groupToDelete) {
      await deleteGroup(groupToDelete.id);
      setGroupToDelete(null);
      setIsDeleteGroupDialogOpen(false);
    }
  };

  // --- DnD handlers (DockingLayout pattern) ---

  const resolveChipGroupId = (chipEl: Element): string | null => {
    const groupSection = chipEl.closest("[data-action-group]");
    return groupSection ? groupSection.getAttribute("data-action-group") : null;
  };

  const computeDropTarget = (
    pointerX: number,
    pointerY: number,
    dragType: "action" | "group",
  ): DropTargetInfo | null => {
    type Candidate = { dist: number; target: DropTargetInfo };
    const candidates: Array<Candidate> = [];

    if (dragType === "group") {
      // Group drag: only target other group headers (vertical ordering)
      const groupEls = document.querySelectorAll("[data-group-header]");
      for (let i = 0; i < groupEls.length; i++) {
        const id = groupEls[i].getAttribute("data-group-header")!;
        if (`group:${id}` === activeDragId) continue;
        const rect = groupEls[i].getBoundingClientRect();
        const centerY = rect.top + rect.height / 2;
        const dist = Math.abs(pointerY - centerY);
        const position = pointerY < centerY ? "before" : "after";
        candidates.push({ dist, target: { id, type: "group", position, groupId: null } });
      }
    } else {
      // Action drag: target action chips and empty group drop zones
      const chipEls = document.querySelectorAll("[data-action-chip]");
      for (let i = 0; i < chipEls.length; i++) {
        const id = chipEls[i].getAttribute("data-action-chip")!;
        if (id === activeDragId) continue;
        const rect = chipEls[i].getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const dist = Math.hypot(pointerX - centerX, pointerY - centerY);
        const position = pointerX < centerX ? "before" : "after";
        const groupId = resolveChipGroupId(chipEls[i]);
        candidates.push({ dist, target: { id, type: "action", position, groupId } });
      }

      // Empty group drop zones — use distance to nearest edge so the entire zone is easy to hit
      const emptyZones = document.querySelectorAll("[data-empty-group-drop]");
      for (let i = 0; i < emptyZones.length; i++) {
        const rect = emptyZones[i].getBoundingClientRect();
        const clampedX = Math.max(rect.left, Math.min(pointerX, rect.right));
        const clampedY = Math.max(rect.top, Math.min(pointerY, rect.bottom));
        const dist = Math.hypot(pointerX - clampedX, pointerY - clampedY);
        const groupId = emptyZones[i].getAttribute("data-empty-group-drop")!;
        candidates.push({ dist, target: { id: groupId, type: "empty-group", position: "before", groupId } });
      }
    }

    if (candidates.length === 0) return null;

    // Return the closest candidate
    candidates.sort((a, b) => a.dist - b.dist);
    return candidates[0].target;
  };

  const handleDragStart = (event: DragStartEvent): void => {
    setActiveDragId(event.active.id as string);
    setDropTarget(null);
    dropTargetRef.current = null;
  };

  const handleDragMove = (event: DragMoveEvent): void => {
    const activeData = event.active.data.current as { type: "action" | "group" } | undefined;
    if (!activeData) return;

    const pointerX = event.activatorEvent instanceof PointerEvent ? event.activatorEvent.clientX + event.delta.x : 0;
    const pointerY = event.activatorEvent instanceof PointerEvent ? event.activatorEvent.clientY + event.delta.y : 0;

    const next = computeDropTarget(pointerX, pointerY, activeData.type);

    const prev = dropTargetRef.current;
    if (prev?.id !== next?.id || prev?.position !== next?.position || prev?.groupId !== next?.groupId) {
      dropTargetRef.current = next;
      setDropTarget(next);
    }
  };

  const handleDragEnd = (event: DragEndEvent): void => {
    const currentDropTarget = dropTargetRef.current;
    setActiveDragId(null);
    setDropTarget(null);
    dropTargetRef.current = null;

    if (!currentDropTarget) return;

    const activeId = event.active.id as string;

    if (currentDropTarget.type === "group") {
      // Group reorder: activeId is "group:<id>", strip prefix
      const groupId = activeId.replace(/^group:/, "");
      const sorted = getSortedGroups();
      const targetIndex = sorted.findIndex((g) => g.id === currentDropTarget.id);
      if (targetIndex === -1) return;
      const newIndex = currentDropTarget.position === "after" ? targetIndex + 1 : targetIndex;
      reorderGroups(groupId, newIndex);
    } else if (currentDropTarget.type === "action") {
      const targetGroupId = currentDropTarget.groupId;
      const targetGroupActions =
        targetGroupId === null ? [...getUngroupedActions()] : [...getActionsInGroup(targetGroupId)];
      const targetIndex = targetGroupActions.findIndex((a) => a.id === currentDropTarget.id);
      if (targetIndex === -1) return;
      const newIndex = currentDropTarget.position === "after" ? targetIndex + 1 : targetIndex;
      reorderActions(activeId, newIndex, targetGroupId);
    } else if (currentDropTarget.type === "empty-group") {
      const targetGroupId = currentDropTarget.groupId;
      reorderActions(activeId, 0, targetGroupId);
    }
  };

  const handleDragCancel = (): void => {
    setActiveDragId(null);
    setDropTarget(null);
    dropTargetRef.current = null;
  };

  const isGroupDrag = activeDragId?.startsWith("group:") ?? false;
  const activeDragAction = !isGroupDrag && activeDragId ? actions.find((a) => a.id === activeDragId) : null;
  const activeDragGroup =
    isGroupDrag && activeDragId ? groups.find((g) => g.id === activeDragId.replace(/^group:/, "")) : null;
  const isActionDrag = activeDragAction != null;

  const renderChip = (action: CustomAction): ReactElement => {
    const chipDropPosition =
      dropTarget && dropTarget.type === "action" && dropTarget.id === action.id ? dropTarget.position : undefined;
    return (
      <DraggableActionChip
        key={action.id}
        action={action}
        onClick={() => handleActionClick(action)}
        disabled={chatActions.isDisabled}
        groups={groups}
        onEdit={handleEditAction}
        onDelete={handleDeleteAction}
        onMoveToGroup={handleMoveToGroup}
        isAgentRunning={isAgentRunning}
        onQueueMessage={handleQueueMessage}
        dropPosition={chipDropPosition}
        isDragSource={activeDragId === action.id}
      />
    );
  };

  return (
    <>
      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragMove={handleDragMove}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <ContextMenu.Root>
          <ContextMenu.Trigger>
            <Flex direction="column" className={styles.panel} height="100%" data-testid={ElementIds.ACTIONS_PANEL}>
              <PanelHeader
                title="Actions"
                actions={
                  <Button
                    variant="ghost"
                    size="1"
                    onClick={handleAddAction}
                    data-testid={ElementIds.ACTIONS_PANEL_ADD_BUTTON}
                  >
                    <Plus size={16} />
                  </Button>
                }
              />

              <div className={styles.scrollArea}>
                <Flex direction="column" p="4" gap="2" className={styles.scrollContent}>
                  {sortedGroups.map((group) => {
                    const groupActions = getDisplayActionsInGroup(group.id);
                    const isCollapsed = collapsedGroups[group.id] ?? false;
                    const isEmptyGroupTarget = dropTarget?.type === "empty-group" && dropTarget.id === group.id;
                    const groupDropPosition =
                      dropTarget && dropTarget.type === "group" && dropTarget.id === group.id
                        ? dropTarget.position
                        : undefined;

                    return (
                      <Flex
                        key={group.id}
                        direction="column"
                        gap="1"
                        mb={!isCollapsed ? "2" : "0"}
                        data-action-group={group.id}
                      >
                        <DraggableGroupHeader
                          group={group}
                          actionCount={groupActions.length}
                          isCollapsed={isCollapsed}
                          isRenaming={renamingGroupId === group.id}
                          renamingGroupName={renamingGroupName}
                          onRenamingGroupNameChange={setRenamingGroupName}
                          onRenameSubmit={handleRenameGroupSubmit}
                          onRenameCancel={handleRenameGroupCancel}
                          onToggleCollapse={() => toggleGroupCollapse(group.id)}
                          onRename={handleRenameGroup}
                          onDelete={handleDeleteGroup}
                          dropPosition={groupDropPosition}
                          isDragSource={activeDragId === `group:${group.id}`}
                        />
                        {!isCollapsed && groupActions.length === 0 && isActionDrag ? (
                          <div
                            className={[styles.emptyGroupDrop, isEmptyGroupTarget ? styles.emptyGroupDropActive : ""]
                              .filter(Boolean)
                              .join(" ")}
                            data-empty-group-drop={group.id}
                          >
                            <Text size="1" className={styles.dropHintText}>
                              Drop action here
                            </Text>
                          </div>
                        ) : !isCollapsed ? (
                          <Flex className={styles.chipGrid} wrap="wrap">
                            {groupActions.map(renderChip)}
                          </Flex>
                        ) : null}
                      </Flex>
                    );
                  })}

                  {ungroupedActions.length > 0 && (
                    <Flex className={styles.chipGrid} wrap="wrap">
                      {ungroupedActions.map(renderChip)}
                    </Flex>
                  )}

                  {creatingGroupName !== null && (
                    <Flex direction="column" gap="2">
                      <TextField.Root
                        autoFocus
                        placeholder="New group name"
                        value={creatingGroupName}
                        onChange={(e) => setCreatingGroupName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            handleCreateGroup();
                          } else if (e.key === "Escape") {
                            handleCancelCreateGroup();
                          }
                        }}
                      />
                      <Flex gap="2">
                        <Button size="1" onClick={handleCreateGroup}>
                          Create
                        </Button>
                        <Button size="1" variant="soft" color="gray" onClick={handleCancelCreateGroup}>
                          Cancel
                        </Button>
                      </Flex>
                    </Flex>
                  )}
                </Flex>
              </div>
            </Flex>
          </ContextMenu.Trigger>
          <ContextMenu.Content size="1" onCloseAutoFocus={handleContextMenuCloseAutoFocus}>
            <ContextMenu.Item onSelect={handleAddAction}>Add action</ContextMenu.Item>
            <ContextMenu.Item onSelect={handleAddGroup}>Add group</ContextMenu.Item>
          </ContextMenu.Content>
        </ContextMenu.Root>

        <DragOverlay dropAnimation={null}>
          {activeDragAction && (
            <div className={styles.dragGhost}>
              <ActionChip action={activeDragAction} onClick={() => {}} disabled={false} />
            </div>
          )}
          {activeDragGroup && (
            <div className={styles.dragGhost}>
              <Text size="1" className={styles.groupName} weight="medium">
                {activeDragGroup.name}
              </Text>
            </div>
          )}
        </DragOverlay>
      </DndContext>

      <ActionDialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        action={editingAction}
        groups={groups}
        onSave={handleSaveAction}
      />

      <DeleteActionDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
        actionName={actionToDelete?.name ?? ""}
        onConfirm={handleConfirmDelete}
      />

      <DeleteGroupDialog
        open={isDeleteGroupDialogOpen}
        onOpenChange={setIsDeleteGroupDialogOpen}
        groupName={groupToDelete?.name ?? ""}
        actionNames={groupToDelete ? getActionsInGroup(groupToDelete.id).map((a) => a.name) : []}
        onConfirm={handleConfirmDeleteGroup}
      />
    </>
  );
};

// The single-instance Actions panel for the section/panel shell: a thin, no-prop
// wrapper that gates on the active workspace and renders the existing actions
// content. Keyed on the workspace id so switching workspaces resets local state.
const ActionsPanelForShell = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return null;
  }
  return <ActionsPanel key={workspaceId} />;
};

registerPanelComponent("actions", ActionsPanelForShell);
