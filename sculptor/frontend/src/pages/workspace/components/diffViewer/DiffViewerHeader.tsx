import { Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { BookOpen } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useMemo } from "react";

import { ElementIds } from "~/api";
import type { FileContextMenuContext, FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import styles from "./DiffViewerHeader.module.scss";
import { DiffViewerMenu } from "./DiffViewerMenu.tsx";
import type { RecentFilesScope } from "./FilePathSelect.tsx";
import { FilePathSelect } from "./FilePathSelect.tsx";
import type { DiffViewOptions, TreeViewOptions } from "./types.ts";

type DiffViewerHeaderProps = {
  workspaceId: string;
  filePath: string;
  /** Which panel's recents the path dropdown feeds and re-opens into. */
  recentFilesScope: RecentFilesScope;
  tabFilePath?: string;
  addedLines: number;
  removedLines: number;
  fileStatus: FileStatus | null;
  isBinary: boolean;
  /** The diff view controls in the triple-dot menu. Absent for
   *  file-view / commit-diff selections that have no diff toggles. */
  viewOptions?: DiffViewOptions;
  /** The tree view controls merged into the triple-dot menu. */
  treeOptions?: TreeViewOptions;
  /** Rendered before the breadcrumb — the sidebar-visibility toggle. */
  leadingControl?: ReactNode;
  /** Rendered in the right cluster before the menu (e.g. refresh). */
  trailingActions?: ReactNode;
  /** When set, shows a quick-open icon that opens the file's rendered
   *  markdown view in the Files panel (offered on diff/commit headers). */
  onOpenRenderedMarkdown?: () => void;
};

/**
 * The 41px viewer header: an optional leading control (sidebar toggle), the
 * file breadcrumb, line stats, optional trailing actions, and the single
 * triple-dot options menu.
 */
export const DiffViewerHeader = ({
  workspaceId,
  filePath,
  recentFilesScope,
  tabFilePath,
  addedLines,
  removedLines,
  fileStatus,
  isBinary: isBinaryProp,
  viewOptions,
  treeOptions,
  leadingControl,
  trailingActions,
  onOpenRenderedMarkdown,
}: DiffViewerHeaderProps): ReactElement => {
  const isBinary = isBinaryProp || isBinaryFile(filePath.split("/").pop() ?? "");

  const fileContext: FileContextMenuContext = useMemo(
    () => ({
      filePath,
      isFolder: false,
      fileStatus: fileStatus ?? undefined,
      isBinary,
      source: "diff-header" as const,
      tabFilePath,
    }),
    [filePath, fileStatus, isBinary, tabFilePath],
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
      <FilePathSelect workspaceId={workspaceId} filePath={filePath} recentFilesScope={recentFilesScope} />

      <span className={styles.spacer} />

      {(addedLines > 0 || removedLines > 0) && (
        <span className={styles.lineStats}>
          <span className={styles.lineStatsAdded}>+{addedLines}</span>
          <span className={styles.lineStatsRemoved}>-{removedLines}</span>
        </span>
      )}

      {onOpenRenderedMarkdown && (
        <Tooltip content="Open rendered markdown">
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            onClick={onOpenRenderedMarkdown}
            aria-label="Open rendered markdown"
            data-testid={ElementIds.DIFF_OPEN_RENDERED_MARKDOWN}
          >
            <BookOpen size={14} />
          </IconButton>
        </Tooltip>
      )}

      {trailingActions}

      <DiffViewerMenu
        workspaceId={workspaceId}
        fileContext={fileContext}
        viewOptions={viewOptions}
        treeOptions={treeOptions}
        isBinary={isBinary}
      />
    </Flex>
  );
};
