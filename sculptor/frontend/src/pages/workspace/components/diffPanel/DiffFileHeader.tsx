import { DropdownMenu, Flex, IconButton } from "@radix-ui/themes";
import { MoreHorizontal, Search, SplitSquareHorizontal } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import { FileDropdownMenu } from "~/pages/workspace/panels/fileBrowser/FileDropdownMenu.tsx";
import type { FileContextMenuContext, FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import styles from "./DiffFileHeader.module.scss";
import type { DiffViewType } from "./types.ts";

/**
 * The diff view controls that previously lived in a toolbar above the viewer.
 * They now hang off the file header's "…" menu (REQ-DIFF polish).
 */
export type DiffViewOptions = {
  viewType: DiffViewType;
  onToggleViewType: () => void;
  lineWrapping: "wrap" | "scroll";
  onToggleLineWrapping: () => void;
  onToggleSearch: () => void;
  showRenderToggle: boolean;
  isRendered: boolean;
  isRenderToggleEnabled: boolean;
  onToggleRender: () => void;
};

type DiffFileHeaderProps = {
  workspaceId: string;
  filePath: string;
  tabFilePath?: string;
  addedLines: number;
  removedLines: number;
  fileStatus: FileStatus | null;
  isBinary: boolean;
  viewOptions?: DiffViewOptions;
  /** Rendered before the breadcrumb (e.g. the master-detail tree toggle). */
  leadingControl?: ReactNode;
  /** Rendered in the right-hand cluster before the "…" menu (e.g. refresh). */
  extraActions?: ReactNode;
  /** Dropdown items prepended to the "…" menu (e.g. the tree view-options,
   *  merged so there is a single options menu). */
  menuLeadingItems?: ReactNode;
};

export const DiffFileHeader = ({
  workspaceId,
  filePath,
  tabFilePath,
  addedLines,
  removedLines,
  fileStatus,
  isBinary: isBinaryProp,
  viewOptions,
  leadingControl,
  extraActions,
  menuLeadingItems,
}: DiffFileHeaderProps): ReactElement => {
  const { dirParts, fileName } = useMemo(() => {
    const parts = filePath.split("/");
    return { dirParts: parts.slice(0, -1), fileName: parts[parts.length - 1] };
  }, [filePath]);

  const menuContext: FileContextMenuContext = useMemo(
    () => ({
      filePath,
      isFolder: false,
      fileStatus: fileStatus ?? undefined,
      isBinary: isBinaryProp || isBinaryFile(filePath.split("/").pop() ?? ""),
      source: "diff-header" as const,
      tabFilePath,
    }),
    [filePath, fileStatus, isBinaryProp, tabFilePath],
  );

  return (
    <Flex
      align="center"
      gap="2"
      px="3"
      flexShrink="0"
      className={styles.header}
      data-testid={ElementIds.DIFF_FILE_HEADER}
    >
      {leadingControl}
      <Flex align="center" gap="0" className={styles.breadcrumb}>
        {dirParts.length > 0 && (
          <>
            <span className={styles.dirPath}>
              {dirParts.map((part, index) => (
                <span key={index}>
                  {index > 0 && <span className={styles.separator}>/</span>}
                  <span className={styles.segment}>{part}</span>
                </span>
              ))}
            </span>
            <span className={styles.separator}>/</span>
          </>
        )}
        <span className={styles.fileName}>{fileName}</span>
      </Flex>

      <span className={styles.spacer} />

      {(addedLines > 0 || removedLines > 0) && (
        <span className={styles.lineStats}>
          <span className={styles.lineStatsAdded}>+{addedLines}</span>
          <span className={styles.lineStatsRemoved}>-{removedLines}</span>
        </span>
      )}

      {extraActions}

      <FileDropdownMenu
        context={menuContext}
        workspaceId={workspaceId}
        leadingItems={
          menuLeadingItems || viewOptions ? (
            <>
              {menuLeadingItems}
              {menuLeadingItems && viewOptions && <DropdownMenu.Separator />}
              {viewOptions && <DiffViewMenuItems isBinary={menuContext.isBinary} options={viewOptions} />}
            </>
          ) : undefined
        }
      >
        <IconButton variant="ghost" size="1" color="gray" data-testid={ElementIds.DIFF_FILE_HEADER_MENU_TRIGGER}>
          <MoreHorizontal size={14} />
        </IconButton>
      </FileDropdownMenu>
    </Flex>
  );
};

/** View controls (find, split/unified, wrap, render) for the "…" menu. Closing
 * tabs lives in the shared "Close" submenu of the file actions below. */
const DiffViewMenuItems = ({ isBinary, options }: { isBinary: boolean; options: DiffViewOptions }): ReactElement => (
  <>
    {!isBinary && (
      <>
        <DropdownMenu.Item onSelect={() => options.onToggleSearch()}>
          <Search size={14} /> Find in file
        </DropdownMenu.Item>
        <DropdownMenu.Item onSelect={() => options.onToggleViewType()}>
          <SplitSquareHorizontal size={14} /> {options.viewType === "split" ? "Unified view" : "Split view"}
        </DropdownMenu.Item>
      </>
    )}
    <DropdownMenu.CheckboxItem
      checked={options.lineWrapping === "wrap"}
      onCheckedChange={() => options.onToggleLineWrapping()}
    >
      Wrap lines
    </DropdownMenu.CheckboxItem>
    {options.showRenderToggle && (
      <DropdownMenu.CheckboxItem
        checked={options.isRendered}
        disabled={!options.isRenderToggleEnabled}
        onCheckedChange={() => options.onToggleRender()}
      >
        Render markdown
      </DropdownMenu.CheckboxItem>
    )}
  </>
);
