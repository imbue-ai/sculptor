import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement, ReactNode } from "react";

import type { FileContextMenuContext } from "./types.ts";
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
          <span key={groupIndex}>
            {groupIndex > 0 && <ContextMenu.Separator />}
            {group.map((entry) =>
              entry.kind === "submenu" ? (
                <ContextMenu.Sub key={entry.key}>
                  <ContextMenu.SubTrigger data-testid={entry.key}>
                    {entry.icon}
                    {entry.label}
                  </ContextMenu.SubTrigger>
                  <ContextMenu.SubContent>
                    {entry.items.map((item) => (
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
                  </ContextMenu.SubContent>
                </ContextMenu.Sub>
              ) : (
                <ContextMenu.Item
                  key={entry.key}
                  disabled={entry.disabled}
                  onSelect={entry.handleSelect}
                  data-testid={entry.key}
                >
                  {entry.icon}
                  {entry.label}
                </ContextMenu.Item>
              ),
            )}
          </span>
        ))}
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
