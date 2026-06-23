import { Flex, IconButton } from "@radix-ui/themes";
import { MoreHorizontal } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import { FileDropdownMenu } from "~/pages/workspace/panels/fileBrowser/FileDropdownMenu.tsx";
import type { FileContextMenuContext, FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import styles from "./DiffFileHeader.module.scss";

type DiffFileHeaderProps = {
  workspaceId: string;
  filePath: string;
  tabFilePath?: string;
  addedLines: number;
  removedLines: number;
  fileStatus?: FileStatus;
  isBinary: boolean;
};

export const DiffFileHeader = ({
  workspaceId,
  filePath,
  tabFilePath,
  addedLines,
  removedLines,
  fileStatus,
  isBinary: isBinaryProp,
}: DiffFileHeaderProps): ReactElement => {
  const { dirParts, fileName } = useMemo(() => {
    const parts = filePath.split("/");
    return { dirParts: parts.slice(0, -1), fileName: parts[parts.length - 1] };
  }, [filePath]);

  const menuContext: FileContextMenuContext = useMemo(
    () => ({
      filePath,
      isFolder: false,
      fileStatus,
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
      <Flex align="center" gap="0" className={styles.breadcrumb}>
        {dirParts.length > 0 && (
          <>
            <span className={styles.dirPath}>
              {dirParts.map((part, index) => (
                <span key={dirParts.slice(0, index + 1).join("/")}>
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

      <FileDropdownMenu context={menuContext} workspaceId={workspaceId}>
        <IconButton variant="ghost" size="1" color="gray" data-testid={ElementIds.DIFF_FILE_HEADER_MENU_TRIGGER}>
          <MoreHorizontal size={14} />
        </IconButton>
      </FileDropdownMenu>
    </Flex>
  );
};
