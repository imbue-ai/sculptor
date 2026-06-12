import { useDraggable } from "@dnd-kit/core";
import { Box, Flex, IconButton, Text, TextField } from "@radix-ui/themes";
import { GripVertical, Pencil, Trash2 } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useState } from "react";

import { type CustomAction, type CustomActionGroup, ElementIds } from "../../../api";
import styles from "./ActionGroupSection.module.scss";
import { ActionSettingsRow } from "./ActionSettingsRow.tsx";

type DropPosition = "before" | "after" | undefined;

type DropTargetInfo = {
  id: string;
  type: "action" | "group" | "empty-group";
  position: "before" | "after";
  groupId?: string | null;
};

type ActionGroupSectionProps = {
  group: CustomActionGroup;
  actions: ReadonlyArray<CustomAction>;
  onEditAction: (action: CustomAction) => void;
  onDeleteAction: (action: CustomAction) => void;
  onRenameGroup: (groupId: string, name: string) => Promise<void>;
  onDeleteGroup: (groupId: string) => void;
  dropPosition?: DropPosition;
  isDragSource?: boolean;
  activeDragId?: string | null;
  isActionDrag?: boolean;
  dropTarget?: DropTargetInfo | null;
};

export const ActionGroupSection = ({
  group,
  actions,
  onEditAction,
  onDeleteAction,
  onRenameGroup,
  onDeleteGroup,
  dropPosition,
  isDragSource,
  activeDragId,
  isActionDrag,
  dropTarget,
}: ActionGroupSectionProps): ReactElement => {
  const [isRenaming, setIsRenaming] = useState(false);
  const [newName, setNewName] = useState(group.name);

  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: group.id,
    data: { type: "group" },
  });

  const handleRenameClick = (): void => {
    setNewName(group.name);
    setIsRenaming(true);
  };

  const handleRenameSubmit = async (): Promise<void> => {
    if (newName.trim() && newName.trim() !== group.name) {
      try {
        await onRenameGroup(group.id, newName.trim());
      } catch (error) {
        console.error("Failed to rename group:", error);
      }
    }
    setIsRenaming(false);
  };

  const handleRenameCancel = (): void => {
    setNewName(group.name);
    setIsRenaming(false);
  };

  const handleRenameKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === "Enter") {
      handleRenameSubmit();
    } else if (e.key === "Escape") {
      handleRenameCancel();
    }
  };

  const handleDeleteGroup = async (): Promise<void> => {
    try {
      await onDeleteGroup(group.id);
    } catch (error) {
      console.error("Failed to delete group:", error);
    }
  };

  const wrapperClassName = [
    styles.groupWrapper,
    dropPosition === "before" ? styles.dropBefore : "",
    dropPosition === "after" ? styles.dropAfter : "",
  ]
    .filter(Boolean)
    .join(" ");

  const headerClassName = [styles.groupHeader, isDragging || isDragSource ? styles.dragging : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div ref={setNodeRef} className={wrapperClassName} data-group-section={group.id}>
      <Flex className={headerClassName} align="center" gap="2" mb="2" py="2" px="2">
        <Box className={styles.dragHandle} {...listeners} {...attributes}>
          <GripVertical size={16} />
        </Box>

        {isRenaming ? (
          <TextField.Root
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={handleRenameKeyDown}
            autoFocus
            style={{ flex: 1 }}
          />
        ) : (
          <Text weight="medium" size="3" style={{ flex: 1 }} data-testid={ElementIds.SETTINGS_ACTIONS_GROUP_HEADING}>
            {group.name}
          </Text>
        )}

        <Flex gap="2" style={{ color: "var(--accent-9)" }}>
          <IconButton variant="ghost" size="1" onClick={handleRenameClick}>
            <Pencil size={14} />
          </IconButton>
          <IconButton
            variant="ghost"
            size="1"
            onClick={handleDeleteGroup}
            data-testid={ElementIds.SETTINGS_GROUP_DELETE_BUTTON}
          >
            <Trash2 size={14} />
          </IconButton>
        </Flex>
      </Flex>

      <Box pl="5">
        {actions.length === 0 && isActionDrag ? (
          <div
            className={[
              styles.emptyGroupDrop,
              dropTarget?.type === "empty-group" && dropTarget.id === group.id ? styles.emptyGroupDropActive : "",
            ]
              .filter(Boolean)
              .join(" ")}
            data-empty-group-drop={group.id}
          >
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              Drop action here
            </Text>
          </div>
        ) : (
          actions.map((action) => {
            const actionDropPosition =
              dropTarget && dropTarget.type === "action" && dropTarget.id === action.id
                ? dropTarget.position
                : undefined;
            const isActionDragSource = activeDragId === action.id;

            return (
              <ActionSettingsRow
                key={action.id}
                action={action}
                onEdit={onEditAction}
                onDelete={onDeleteAction}
                dropPosition={actionDropPosition}
                isDragSource={isActionDragSource}
              />
            );
          })
        )}
      </Box>
    </div>
  );
};
