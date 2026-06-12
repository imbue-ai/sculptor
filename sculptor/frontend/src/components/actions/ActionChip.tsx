import { Tooltip } from "@radix-ui/themes";
import { Play, TextCursorInput } from "lucide-react";
import type { ReactElement } from "react";

import type { CustomAction, CustomActionGroup } from "~/api";
import { ElementIds } from "~/api";

import styles from "./ActionChip.module.scss";
import { ActionContextMenu } from "./ActionContextMenu";

type ActionChipProps = {
  action: CustomAction;
  onClick: () => void;
  disabled?: boolean;
  groups?: ReadonlyArray<CustomActionGroup>;
  onEdit?: (action: CustomAction) => void;
  onDelete?: (action: CustomAction) => void;
  onMoveToGroup?: (action: CustomAction, groupId: string | null) => void;
  isAgentRunning?: boolean;
  onQueueMessage?: (prompt: string) => void;
  isDragging?: boolean;
};

export const ActionChip = ({
  action,
  onClick,
  disabled,
  groups = [],
  onEdit,
  onDelete,
  onMoveToGroup,
  isAgentRunning,
  onQueueMessage,
  isDragging,
}: ActionChipProps): ReactElement => {
  const handleClick = (e: React.MouseEvent<HTMLButtonElement>): void => {
    if (disabled) {
      e.preventDefault();
      return;
    }
    onClick();
  };

  const isAutoSubmit = action.autoSubmit ?? true;

  const hasContextMenu = onEdit && onDelete && onMoveToGroup;
  const tooltipContent = action.prompt || undefined;

  const chipButton = (
    <button
      className={`${styles.chip} ${disabled ? styles.disabled : ""} ${isDragging ? styles.dragging : ""}`}
      onClick={handleClick}
      aria-disabled={disabled}
      type="button"
      data-testid={ElementIds.ACTION_CHIP}
    >
      {isAutoSubmit ? (
        <Play className={styles.autoSubmitIcon} size={14} />
      ) : (
        <TextCursorInput className={styles.draftIcon} size={14} />
      )}
      <span>{action.name}</span>
    </button>
  );

  if (hasContextMenu) {
    // Tooltip must be *outside* ActionContextMenu, not wrapping the button
    // inside ContextMenu.Trigger. Radix Tooltip inserts a wrapper <span> that
    // intercepts pointer events and breaks ContextMenu.Trigger's right-click
    // handling. We wrap ActionContextMenu in a <span> so Tooltip has a DOM
    // node to attach its ref to (ContextMenu.Root is a non-visual provider).
    const contextMenu = (
      <ActionContextMenu
        action={action}
        groups={groups}
        onEdit={onEdit}
        onDelete={onDelete}
        onMoveToGroup={onMoveToGroup}
        isAgentRunning={isAgentRunning}
        onQueueMessage={onQueueMessage}
      >
        {chipButton}
      </ActionContextMenu>
    );

    if (tooltipContent) {
      return (
        <Tooltip content={tooltipContent}>
          <span>{contextMenu}</span>
        </Tooltip>
      );
    }
    return contextMenu;
  }

  if (tooltipContent) {
    return <Tooltip content={tooltipContent}>{chipButton}</Tooltip>;
  }
  return chipButton;
};
