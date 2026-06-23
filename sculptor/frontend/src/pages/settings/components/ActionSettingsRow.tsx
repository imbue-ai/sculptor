import { useDraggable } from "@dnd-kit/core";
import { Badge, Box, Flex, IconButton, Text } from "@radix-ui/themes";
import { GripVertical, Pencil, Trash2 } from "lucide-react";
import type { ReactElement } from "react";

import type { CustomAction } from "../../../api";
import { ElementIds } from "../../../api";
import styles from "./ActionSettingsRow.module.scss";

type DropPosition = "before" | "after";

type ActionSettingsRowProps = {
  action: CustomAction;
  onEdit: (action: CustomAction) => void;
  onDelete: (action: CustomAction) => void;
  dropPosition?: DropPosition;
  isDragSource?: boolean;
};

export const ActionSettingsRow = ({
  action,
  onEdit,
  onDelete,
  dropPosition,
  isDragSource,
}: ActionSettingsRowProps): ReactElement => {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: action.id,
    data: { type: "action", groupId: action.groupId },
  });

  const wrapperClassName = [
    styles.rowWrapper,
    dropPosition === "before" ? styles.dropBefore : "",
    dropPosition === "after" ? styles.dropAfter : "",
  ]
    .filter(Boolean)
    .join(" ");

  const rowClassName = [styles.actionRow, isDragging || isDragSource ? styles.dragging : ""].filter(Boolean).join(" ");

  return (
    <div
      ref={setNodeRef}
      className={wrapperClassName}
      data-action-row={action.id}
      data-testid={ElementIds.SETTINGS_ACTION_ROW}
    >
      <Flex className={rowClassName} align="center" gap="3" py="1" px="2">
        <Box className={styles.dragHandle} {...listeners} {...attributes}>
          <GripVertical size={16} />
        </Box>

        <Flex direction="column" className={styles.actionInfo}>
          <Text weight="bold" size="2">
            {action.name}
          </Text>
          <Text size="2" className={styles.promptPreview}>
            {action.prompt}
          </Text>
        </Flex>

        <Badge color={action.autoSubmit ? "green" : "gray"} variant="soft">
          {action.autoSubmit ? "Auto-submit" : "Draft"}
        </Badge>

        <Flex className={styles.actionButtons} align="center" gap="2">
          <IconButton
            variant="ghost"
            size="1"
            onClick={() => onEdit(action)}
            data-testid={ElementIds.SETTINGS_ACTION_EDIT_BUTTON}
          >
            <Pencil size={14} />
          </IconButton>
          <IconButton
            variant="ghost"
            size="1"
            onClick={() => onDelete(action)}
            data-testid={ElementIds.SETTINGS_ACTION_DELETE_BUTTON}
          >
            <Trash2 size={14} />
          </IconButton>
        </Flex>
      </Flex>
    </div>
  );
};
