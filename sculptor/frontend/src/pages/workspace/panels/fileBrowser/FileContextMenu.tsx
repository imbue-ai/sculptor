import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import type { FileContextMenuContext } from "./types/fileBrowser.ts";
import { useFileMenuGroups } from "./useFileMenuGroups.tsx";

type FileContextMenuProps = {
  children: ReactNode;
  context: FileContextMenuContext;
  workspaceId: string;
  allDescendantFolderPaths?: Array<string>;
  isExpanded?: boolean;
  onCollapseChildren?: (folderPath: string) => void;
  /** Extra className applied to the ContextMenu.Content element. */
  contentClassName?: string;
};

export const FileContextMenu = ({
  children,
  context,
  workspaceId,
  allDescendantFolderPaths,
  isExpanded,
  onCollapseChildren,
  contentClassName,
}: FileContextMenuProps): ReactElement => {
  const menuGroups = useFileMenuGroups({
    context,
    workspaceId,
    allDescendantFolderPaths,
    isExpanded,
    onCollapseChildren,
  });

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1" className={contentClassName}>
        {menuGroups.map((group, groupIndex) => (
          <span key={group[0].key}>
            {groupIndex > 0 && <ContextMenu.Separator />}
            {group.map((item) => (
              <ContextMenu.Item
                key={item.key}
                disabled={item.disabled}
                onSelect={item.handleSelect}
                data-testid={item.key}
              >
                {item.icon}
                {item.label}
              </ContextMenu.Item>
            ))}
          </span>
        ))}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
