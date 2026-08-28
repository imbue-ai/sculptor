import { DropdownMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";
import { Fragment } from "react";

import type { FileContextMenuContext } from "./types/fileBrowser.ts";
import { useFileMenuGroups } from "./useFileMenuGroups.tsx";

type FileDropdownMenuProps = {
  children: ReactNode;
  context: FileContextMenuContext;
  workspaceId: string;
};

export const FileDropdownMenu = ({ children, context, workspaceId }: FileDropdownMenuProps): ReactElement => {
  const menuGroups = useFileMenuGroups({ context, workspaceId });

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>{children}</DropdownMenu.Trigger>
      <DropdownMenu.Content size="1">
        {menuGroups.map((group, groupIndex) => (
          <Fragment key={group[0].key}>
            {groupIndex > 0 && <DropdownMenu.Separator />}
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
          </Fragment>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
