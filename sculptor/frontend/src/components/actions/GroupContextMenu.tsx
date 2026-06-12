import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import { type CustomActionGroup, ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";

type GroupContextMenuProps = {
  group: CustomActionGroup;
  children: ReactNode;
  onRename: (group: CustomActionGroup) => void;
  onDelete: (group: CustomActionGroup) => void;
};

export const GroupContextMenu = ({ group, children, onRename, onDelete }: GroupContextMenuProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        <ContextMenu.Item onSelect={() => onRename(group)}>Rename group</ContextMenu.Item>

        <ContextMenu.Separator />

        <ContextMenu.Item
          color={dangerColor}
          onSelect={() => onDelete(group)}
          data-testid={ElementIds.GROUP_CONTEXT_MENU_DELETE}
        >
          Delete group
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
