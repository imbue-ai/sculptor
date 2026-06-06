import { DropdownMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import type { FileContextMenuContext } from "./types.ts";
import { useFileMenuGroups } from "./useFileMenuGroups.tsx";

type FileDropdownMenuProps = {
  children: ReactNode;
  context: FileContextMenuContext;
  workspaceId: string;
  /** Extra items rendered at the top of the menu, above the file actions. */
  leadingItems?: ReactNode;
};

export const FileDropdownMenu = ({
  children,
  context,
  workspaceId,
  leadingItems,
}: FileDropdownMenuProps): ReactElement => {
  const menuGroups = useFileMenuGroups({ context, workspaceId });

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>{children}</DropdownMenu.Trigger>
      <DropdownMenu.Content size="1">
        {leadingItems}
        {menuGroups.map((group, groupIndex) => (
          <span key={groupIndex}>
            {(groupIndex > 0 || leadingItems) && <DropdownMenu.Separator />}
            {group.map((item) => (
              <DropdownMenu.Item
                key={item.key}
                disabled={item.disabled}
                onSelect={item.handleSelect}
                data-testid={item.key}
              >
                {item.icon}
                {item.label}
              </DropdownMenu.Item>
            ))}
          </span>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
