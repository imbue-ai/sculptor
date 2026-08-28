import type { DragEndEvent, DragMoveEvent, DragStartEvent } from "@dnd-kit/core";
import { DndContext, DragOverlay, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { Box, Button, Dialog, Flex, Separator, Text, TextField } from "@radix-ui/themes";
import { Download, GripVertical, Plus, Upload } from "lucide-react";
import type { ReactElement } from "react";
import { useRef, useState } from "react";

import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";
import { useCustomActions } from "~/common/state/hooks/useCustomActions.ts";
import { useUserConfig } from "~/common/state/hooks/useUserConfig.ts";
import { HTTPException } from "~/common/utils/errors.ts";
import type { ActionFormData } from "~/components/actions/ActionDialog.tsx";
import { ActionDialog } from "~/components/actions/ActionDialog.tsx";
import { DeleteActionDialog } from "~/components/actions/DeleteActionDialog.tsx";
import { DeleteGroupDialog } from "~/components/actions/DeleteGroupDialog.tsx";

import type { CustomAction, CustomActionGroup, CustomActionsConfig } from "../../../api";
import { ElementIds } from "../../../api";
import { ActionGroupSection } from "./ActionGroupSection.tsx";
import { ActionSettingsRow } from "./ActionSettingsRow.tsx";
import styles from "./ActionsSettingsSection.module.scss";
import { SettingsSectionLayout } from "./SettingsSection.tsx";

type DropTargetInfo = {
  id: string;
  type: "action" | "group" | "empty-group";
  position: "before" | "after";
  groupId?: string | null;
};

type ActionsSettingsSectionProps = {
  setToast: (toast: ToastContent | null) => void;
};

export const ActionsSettingsSection = ({ setToast }: ActionsSettingsSectionProps): ReactElement => {
  const {
    actions,
    groups,
    addAction,
    addActionWithNewGroup,
    updateAction,
    updateActionWithNewGroup,
    deleteAction,
    addGroup,
    renameGroup,
    deleteGroup,
    reorderActions,
    reorderGroups,
    getActionsInGroup,
    getUngroupedActions,
    getSortedGroups,
  } = useCustomActions();
  const { updateConfig } = useUserConfig();

  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingAction, setEditingAction] = useState<CustomAction | undefined>(undefined);
  const [deletingAction, setDeletingAction] = useState<CustomAction | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isAddGroupOpen, setIsAddGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [deletingGroup, setDeletingGroup] = useState<CustomActionGroup | null>(null);
  const [isDeletingGroup, setIsDeletingGroup] = useState(false);

  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTargetInfo | null>(null);
  const dropTargetRef = useRef<DropTargetInfo | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleAddAction = (): void => {
    setEditingAction(undefined);
    setIsDialogOpen(true);
  };

  const handleEditAction = (action: CustomAction): void => {
    setEditingAction(action);
    setIsDialogOpen(true);
  };

  const handleDeleteAction = (action: CustomAction): void => {
    setDeletingAction(action);
  };

  const handleDeleteConfirm = async (): Promise<void> => {
    if (!deletingAction || isDeleting) return;

    setIsDeleting(true);
    try {
      await deleteAction(deletingAction.id);
      setDeletingAction(null);
      setToast({ type: ToastType.SUCCESS, title: "Action deleted successfully" });
    } catch (error) {
      let errorMessage = "Failed to delete action";
      if (error instanceof HTTPException) {
        errorMessage = error.detail;
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }
      setToast({ type: ToastType.ERROR, title: errorMessage });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteCancel = (): void => {
    if (isDeleting) return;
    setDeletingAction(null);
  };

  const handleSaveAction = async (formData: ActionFormData): Promise<void> => {
    try {
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
        setToast({ type: ToastType.SUCCESS, title: "Action updated successfully" });
      } else if (formData.newGroupName) {
        await addActionWithNewGroup(
          { name: formData.name, prompt: formData.prompt, autoSubmit: formData.autoSubmit },
          formData.newGroupName,
        );
        setToast({ type: ToastType.SUCCESS, title: "Action created successfully" });
      } else {
        await addAction({
          name: formData.name,
          prompt: formData.prompt,
          autoSubmit: formData.autoSubmit,
          groupId: formData.groupId,
        });
        setToast({ type: ToastType.SUCCESS, title: "Action created successfully" });
      }

      setIsDialogOpen(false);
      setEditingAction(undefined);
    } catch (error) {
      let errorMessage = "Failed to save action";
      if (error instanceof HTTPException) {
        errorMessage = error.detail;
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }
      setToast({ type: ToastType.ERROR, title: errorMessage });
    }
  };

  const handleAddGroup = (): void => {
    setNewGroupName("");
    setIsAddGroupOpen(true);
  };

  const handleAddGroupConfirm = async (): Promise<void> => {
    const trimmed = newGroupName.trim();
    if (!trimmed) return;

    try {
      await addGroup(trimmed);
      setIsAddGroupOpen(false);
      setToast({ type: ToastType.SUCCESS, title: "Group created successfully" });
    } catch (error) {
      let errorMessage = "Failed to create group";
      if (error instanceof HTTPException) {
        errorMessage = error.detail;
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }
      setToast({ type: ToastType.ERROR, title: errorMessage });
    }
  };

  const handleDeleteGroup = (groupId: string): void => {
    const group = groups.find((g) => g.id === groupId);
    if (group) {
      setDeletingGroup(group);
    }
  };

  const handleDeleteGroupConfirm = async (): Promise<void> => {
    if (!deletingGroup || isDeletingGroup) return;

    setIsDeletingGroup(true);
    try {
      await deleteGroup(deletingGroup.id);
      setDeletingGroup(null);
      setToast({ type: ToastType.SUCCESS, title: "Group deleted successfully" });
    } catch (error) {
      let errorMessage = "Failed to delete group";
      if (error instanceof HTTPException) {
        errorMessage = error.detail;
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }
      setToast({ type: ToastType.ERROR, title: errorMessage });
    } finally {
      setIsDeletingGroup(false);
    }
  };

  const handleDeleteGroupCancel = (): void => {
    if (isDeletingGroup) return;
    setDeletingGroup(null);
  };

  const handleExport = (): void => {
    const config: CustomActionsConfig = {
      version: 1,
      actions: [...actions],
      groups: [...groups],
    };

    const json = JSON.stringify(config, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sculptor-actions.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = (): void => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json";
    input.onchange = async (e): Promise<void> => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        const imported = JSON.parse(text) as CustomActionsConfig;

        if (!imported.version || !Array.isArray(imported.actions) || !Array.isArray(imported.groups)) {
          throw new Error("Invalid actions file format");
        }

        const groupIdMap = new Map<string, string>();
        const newGroups: Array<CustomActionGroup> = imported.groups.map((group) => {
          const newId = crypto.randomUUID();
          groupIdMap.set(group.id, newId);
          return { ...group, id: newId };
        });

        const newActions: Array<CustomAction> = imported.actions.map((action) => ({
          ...action,
          id: crypto.randomUUID(),
          groupId: action.groupId ? (groupIdMap.get(action.groupId) ?? null) : null,
        }));

        const maxGroupOrder = groups.length > 0 ? Math.max(...groups.map((g) => g.order)) : -1;
        const maxActionOrder = actions.length > 0 ? Math.max(...actions.map((a) => a.order ?? 0)) : -1;

        const adjustedGroups = newGroups.map((g) => ({ ...g, order: g.order + maxGroupOrder + 1 }));
        const adjustedActions = newActions.map((a) => ({ ...a, order: (a.order ?? 0) + maxActionOrder + 1 }));

        const mergedConfig: CustomActionsConfig = {
          version: 1,
          actions: [...actions, ...adjustedActions],
          groups: [...groups, ...adjustedGroups],
        };

        await updateConfig({ customActions: mergedConfig });

        setToast({
          type: ToastType.SUCCESS,
          title: `Imported ${adjustedActions.length} actions and ${adjustedGroups.length} groups`,
        });
      } catch (error) {
        let errorMessage = "Failed to import actions";
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        setToast({ type: ToastType.ERROR, title: errorMessage });
      }
    };
    input.click();
  };

  const resolveActionGroupId = (rowEl: Element): string | null => {
    // Walk up to find the parent group section, if any
    const groupSection = rowEl.closest("[data-group-section]");
    return groupSection ? groupSection.getAttribute("data-group-section") : null;
  };

  const computeDropTarget = (pointerY: number, dragType: "action" | "group"): DropTargetInfo | null => {
    if (dragType === "action") {
      // Collect all candidate drop targets: action rows + empty group drop zones
      type Candidate = { centerY: number; target: DropTargetInfo };
      const candidates: Array<Candidate> = [];

      // Action rows across all groups and ungrouped
      const rowEls = document.querySelectorAll("[data-action-row]");
      for (let i = 0; i < rowEls.length; i++) {
        const rect = rowEls[i].getBoundingClientRect();
        const centerY = rect.top + rect.height / 2;
        const id = rowEls[i].getAttribute("data-action-row")!;
        const groupId = resolveActionGroupId(rowEls[i]);
        candidates.push({ centerY, target: { id, type: "action", position: "before", groupId } });
      }

      // Empty group drop zones
      const emptyZones = document.querySelectorAll("[data-empty-group-drop]");
      for (let i = 0; i < emptyZones.length; i++) {
        const rect = emptyZones[i].getBoundingClientRect();
        const centerY = rect.top + rect.height / 2;
        const groupId = emptyZones[i].getAttribute("data-empty-group-drop")!;
        candidates.push({ centerY, target: { id: groupId, type: "empty-group", position: "before", groupId } });
      }

      if (candidates.length === 0) return null;

      // Sort by vertical position
      candidates.sort((a, b) => a.centerY - b.centerY);

      // Find closest candidate
      for (let i = 0; i < candidates.length; i++) {
        if (pointerY < candidates[i].centerY) {
          const target = candidates[i].target;
          // For action rows, pointer is above center → "before"
          if (target.type === "action") {
            return { ...target, position: "before" };
          }
          return target;
        }
      }

      // Pointer is below all candidates → last one
      const last = candidates[candidates.length - 1].target;
      if (last.type === "action") {
        return { ...last, position: "after" };
      }
      return last;
    }

    if (dragType === "group") {
      const groupEls = document.querySelectorAll("[data-group-section]");
      if (groupEls.length === 0) return null;

      for (let i = 0; i < groupEls.length; i++) {
        const rect = groupEls[i].getBoundingClientRect();
        const centerY = rect.top + rect.height / 2;
        if (pointerY < centerY) {
          return { id: groupEls[i].getAttribute("data-group-section")!, type: "group", position: "before" };
        }
      }
      const lastEl = groupEls[groupEls.length - 1];
      return { id: lastEl.getAttribute("data-group-section")!, type: "group", position: "after" };
    }

    return null;
  };

  const handleDragStart = (event: DragStartEvent): void => {
    setActiveDragId(event.active.id as string);
    setDropTarget(null);
    dropTargetRef.current = null;
  };

  const handleDragMove = (event: DragMoveEvent): void => {
    const activeData = event.active.data.current as { type: "action" | "group"; groupId?: string | null } | undefined;
    if (!activeData) return;

    const pointerY = event.activatorEvent instanceof PointerEvent ? event.activatorEvent.clientY + event.delta.y : 0;
    const next = computeDropTarget(pointerY, activeData.type);

    const prev = dropTargetRef.current;
    if (prev?.id !== next?.id || prev?.position !== next?.position) {
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

    const activeData = event.active.data.current as { type: "action" | "group"; groupId?: string | null } | undefined;
    if (!activeData) return;

    const activeId = event.active.id as string;

    if (activeData.type === "group" && currentDropTarget.type === "group") {
      const sorted = getSortedGroups();
      const targetIndex = sorted.findIndex((g) => g.id === currentDropTarget.id);
      if (targetIndex === -1) return;
      const newIndex = currentDropTarget.position === "after" ? targetIndex + 1 : targetIndex;
      reorderGroups(activeId, newIndex);
    } else if (activeData.type === "action" && currentDropTarget.type === "action") {
      // Use the drop target's group (where we're dropping), not the drag source's group
      const targetGroupId = currentDropTarget.groupId ?? null;
      const targetGroupActions =
        targetGroupId === null ? [...getUngroupedActions()] : [...getActionsInGroup(targetGroupId)];
      const targetIndex = targetGroupActions.findIndex((a) => a.id === currentDropTarget.id);
      if (targetIndex === -1) return;
      const newIndex = currentDropTarget.position === "after" ? targetIndex + 1 : targetIndex;
      reorderActions(activeId, newIndex, targetGroupId);
    } else if (activeData.type === "action" && currentDropTarget.type === "empty-group") {
      // Drop into an empty group at position 0
      const targetGroupId = currentDropTarget.groupId ?? null;
      reorderActions(activeId, 0, targetGroupId);
    }
  };

  const handleDragCancel = (): void => {
    setActiveDragId(null);
    setDropTarget(null);
    dropTargetRef.current = null;
  };

  const ungroupedActions = getUngroupedActions();
  const sortedGroups = getSortedGroups();
  const hasContent = actions.length > 0 || groups.length > 0;

  // Resolve drag overlay label and type
  const activeDragAction = activeDragId ? actions.find((a) => a.id === activeDragId) : null;
  const activeDragGroup = activeDragId ? groups.find((g) => g.id === activeDragId) : null;
  const dragOverlayLabel = activeDragAction?.name ?? activeDragGroup?.name ?? null;
  const isActionDrag = activeDragAction != null;

  return (
    <>
      <SettingsSectionLayout
        description={
          <>
            <strong>Experimental:</strong> Define custom snippets or macros for the Actions panel.
          </>
        }
      >
        <Flex direction="column" className={styles.actionsSection} data-testid={ElementIds.SETTINGS_ACTIONS_SECTION}>
          <Flex gap="2" mb="4" wrap="wrap" className={styles.toolbar}>
            <Button variant="solid" onClick={handleAddAction} data-testid={ElementIds.SETTINGS_ACTIONS_ADD_BUTTON}>
              <Plus size={16} />
              Add Action
            </Button>
            <Button variant="soft" onClick={handleAddGroup} data-testid={ElementIds.SETTINGS_ACTIONS_ADD_GROUP_BUTTON}>
              <Plus size={16} />
              Add Group
            </Button>
            <Box style={{ flex: 1 }} />
            <Button
              variant="soft"
              onClick={handleExport}
              disabled={!hasContent}
              data-testid={ElementIds.SETTINGS_ACTIONS_EXPORT_BUTTON}
            >
              <Download size={16} />
              Export
            </Button>
            <Button variant="soft" onClick={handleImport} data-testid={ElementIds.SETTINGS_ACTIONS_IMPORT_BUTTON}>
              <Upload size={16} />
              Import
            </Button>
          </Flex>

          {!hasContent && (
            <Box className={styles.emptyState}>
              <Text size="2">No actions yet. Create your first action to get started.</Text>
            </Box>
          )}

          {hasContent && (
            <DndContext
              sensors={sensors}
              modifiers={[restrictToVerticalAxis]}
              onDragStart={handleDragStart}
              onDragMove={handleDragMove}
              onDragEnd={handleDragEnd}
              onDragCancel={handleDragCancel}
            >
              <Flex direction="column" gap="4">
                {ungroupedActions.length > 0 && (
                  <Flex direction="column" data-ungrouped-actions>
                    {ungroupedActions.map((action) => {
                      const actionDropPosition =
                        dropTarget && dropTarget.type === "action" && dropTarget.id === action.id
                          ? dropTarget.position
                          : undefined;
                      return (
                        <ActionSettingsRow
                          key={action.id}
                          action={action}
                          onEdit={handleEditAction}
                          onDelete={handleDeleteAction}
                          dropPosition={actionDropPosition}
                          isDragSource={activeDragId === action.id}
                        />
                      );
                    })}
                  </Flex>
                )}

                {ungroupedActions.length > 0 && sortedGroups.length > 0 && (
                  <Separator size="4" className={styles.separator} />
                )}

                {sortedGroups.map((group) => {
                  const groupActions = getActionsInGroup(group.id);
                  const groupDropPosition =
                    dropTarget && dropTarget.type === "group" && dropTarget.id === group.id
                      ? dropTarget.position
                      : undefined;
                  return (
                    <ActionGroupSection
                      key={group.id}
                      group={group}
                      actions={groupActions}
                      onEditAction={handleEditAction}
                      onDeleteAction={handleDeleteAction}
                      onRenameGroup={renameGroup}
                      onDeleteGroup={handleDeleteGroup}
                      dropPosition={groupDropPosition}
                      isDragSource={activeDragId === group.id}
                      activeDragId={activeDragId}
                      isActionDrag={isActionDrag}
                      dropTarget={dropTarget}
                    />
                  );
                })}
              </Flex>

              <DragOverlay dropAnimation={null}>
                {dragOverlayLabel && (
                  <div className={styles.dragOverlay}>
                    <GripVertical size={16} />
                    <Text size="2" weight="medium">
                      {dragOverlayLabel}
                    </Text>
                  </div>
                )}
              </DragOverlay>
            </DndContext>
          )}
        </Flex>
      </SettingsSectionLayout>

      <ActionDialog
        open={isDialogOpen}
        onOpenChange={setIsDialogOpen}
        action={editingAction}
        groups={groups}
        onSave={handleSaveAction}
      />

      <DeleteActionDialog
        open={!!deletingAction}
        onOpenChange={(open: boolean) => !open && handleDeleteCancel()}
        actionName={deletingAction?.name || ""}
        onConfirm={handleDeleteConfirm}
        isDeleting={isDeleting}
      />

      <Dialog.Root open={isAddGroupOpen} onOpenChange={setIsAddGroupOpen}>
        <Dialog.Content style={{ maxWidth: 400 }}>
          <Flex direction="column" gap="4">
            <Dialog.Title>Create New Group</Dialog.Title>
            <TextField.Root
              placeholder="Group name"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleAddGroupConfirm();
                }
              }}
              autoFocus
              data-testid={ElementIds.SETTINGS_ACTIONS_GROUP_NAME_INPUT}
            />
            <Flex gap="3" justify="end">
              <Dialog.Close>
                <Button variant="soft" color="gray">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button
                variant="solid"
                onClick={handleAddGroupConfirm}
                disabled={!newGroupName.trim()}
                data-testid={ElementIds.SETTINGS_ACTIONS_CREATE_GROUP_BUTTON}
              >
                Create Group
              </Button>
            </Flex>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      <DeleteGroupDialog
        open={!!deletingGroup}
        onOpenChange={(open: boolean) => !open && handleDeleteGroupCancel()}
        groupName={deletingGroup?.name ?? ""}
        actionNames={deletingGroup ? getActionsInGroup(deletingGroup.id).map((a) => a.name) : []}
        onConfirm={handleDeleteGroupConfirm}
        isDeleting={isDeletingGroup}
      />
    </>
  );
};
