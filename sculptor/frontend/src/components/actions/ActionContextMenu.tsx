import { ContextMenu, Text } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import type { CustomAction, CustomActionGroup } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

type ActionContextMenuProps = {
  action: CustomAction;
  groups: ReadonlyArray<CustomActionGroup>;
  children: ReactNode;
  onEdit: (action: CustomAction) => void;
  onDelete: (action: CustomAction) => void;
  onMoveToGroup: (action: CustomAction, groupId: string | null) => void;
  isAgentRunning?: boolean;
  onQueueMessage?: (prompt: string) => void;
  onOpenChange?: (open: boolean) => void;
};

// WARNING: Do not wrap this component's children in a <Tooltip>.
// Radix Tooltip inserts a wrapper <span> around its child, which intercepts
// pointer events before ContextMenu.Trigger can process them. This causes
// right-click to open the *parent* context menu instead of this one.
// If you need a tooltip on the trigger element, wrap the Tooltip around
// the entire <ActionContextMenu> instead, or place it outside the Trigger.
export const ActionContextMenu = ({
  action,
  groups,
  children,
  onEdit,
  onDelete,
  onMoveToGroup,
  isAgentRunning,
  onQueueMessage,
  onOpenChange,
}: ActionContextMenuProps): ReactElement => {
  const dangerColor = useThemeDangerColor();

  const handleQueueMessage = (): void => {
    onQueueMessage?.(action.prompt);
  };

  const handleEdit = (): void => {
    onEdit(action);
  };

  const handleDelete = (): void => {
    onDelete(action);
  };

  const handleMoveToGroup = (groupId: string | null): void => {
    onMoveToGroup(action, groupId);
  };

  const isInGroup = (groupId: string): boolean => {
    return action.groupId === groupId;
  };

  const isUngrouped = (): boolean => {
    return !action.groupId;
  };

  return (
    <ContextMenu.Root onOpenChange={onOpenChange}>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        {isAgentRunning && onQueueMessage && (
          <>
            <ContextMenu.Item onSelect={handleQueueMessage}>
              <Text weight="bold">Queue message</Text>
            </ContextMenu.Item>
            <ContextMenu.Separator />
          </>
        )}

        <ContextMenu.Item onSelect={handleEdit}>Edit action</ContextMenu.Item>

        <ContextMenu.Sub>
          <ContextMenu.SubTrigger>Move to group...</ContextMenu.SubTrigger>
          <ContextMenu.SubContent>
            <ContextMenu.Item disabled={isUngrouped()} onSelect={() => handleMoveToGroup(null)}>
              No group
            </ContextMenu.Item>
            {groups.map((group) => (
              <ContextMenu.Item
                key={group.id}
                disabled={isInGroup(group.id)}
                onSelect={() => handleMoveToGroup(group.id)}
              >
                {group.name}
              </ContextMenu.Item>
            ))}
          </ContextMenu.SubContent>
        </ContextMenu.Sub>

        <ContextMenu.Separator />

        <ContextMenu.Item color={dangerColor} onSelect={handleDelete}>
          Delete action
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
