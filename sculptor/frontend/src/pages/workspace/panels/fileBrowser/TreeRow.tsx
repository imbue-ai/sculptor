import { IconButton, Tooltip } from "@radix-ui/themes";
import { AlertTriangle, ChevronRight, Folder, X } from "lucide-react";
import { createElement, memo, type ReactElement } from "react";

import { ElementIds } from "~/api";

import { getFileIcon } from "./fileIcons.ts";
import styles from "./FileTree.module.scss";
import type { TreeNode } from "./types.ts";
import { STATUS_COLOR_STYLES, truncateMiddlePath } from "./utils.ts";

/** Left padding (px) of a depth-0 row. */
const TREE_ROW_BASE_PADDING_LEFT = 12;
/** Extra left padding (px) added per nesting level. */
const TREE_ROW_DEPTH_INDENT = 10;

type TreeRowProps = {
  node: TreeNode;
  depth: number;
  isExpanded: boolean;
  isFocused: boolean;
  isActiveFile: boolean;
  folderChangeCount: number;
  addedLines?: number;
  removedLines?: number;
  /** When set, the parent directory is shown after the file name (used in flat-list mode). */
  parentDir?: string;
  onToggleExpand: (path: string) => void;
  onFileClick: (path: string) => void;
  onDiscardFile?: (filePath: string) => void;
};

const splitFileName = (name: string): { baseName: string; extension: string } => {
  const lastDot = name.lastIndexOf(".");
  if (lastDot <= 0) {
    return { baseName: name, extension: "" };
  }
  return { baseName: name.slice(0, lastDot), extension: name.slice(lastDot) };
};

const FolderIcon = memo(function FolderIcon({ isExpanded }: { isExpanded: boolean }): ReactElement {
  return (
    <>
      <span className={styles.iconArea}>
        <ChevronRight size={14} className={`${styles.chevron} ${isExpanded ? styles.expanded : ""}`} />
      </span>
      <Folder size={14} className={styles.folderIcon} />
    </>
  );
});

const FileTypeIcon = memo(function FileTypeIcon({ filename }: { filename: string }): ReactElement {
  // getFileIcon selects a stable module-level Lucide component; render it via
  // createElement so it reads as choosing a component, not creating one.
  return createElement(getFileIcon(filename), { size: 14, className: styles.fileIcon });
});

const LineStats = ({
  addedLines,
  removedLines,
}: {
  addedLines?: number;
  removedLines?: number;
}): ReactElement | null => {
  const hasAdded = addedLines != null && addedLines > 0;
  const hasRemoved = removedLines != null && removedLines > 0;
  if (!hasAdded && !hasRemoved) return null;

  return (
    <span className={styles.lineStats}>
      {hasAdded && <span className={styles.lineStatsAdded}>+{addedLines}</span>}
      {hasRemoved && <span className={styles.lineStatsRemoved}>-{removedLines}</span>}
    </span>
  );
};

const StatusIndicator = ({
  errorMessage,
  status,
}: {
  errorMessage?: string;
  status: TreeNode["status"];
}): ReactElement | null => {
  if (errorMessage) {
    return (
      <Tooltip content={errorMessage}>
        <span className={styles.warning}>
          <AlertTriangle size={12} />
        </span>
      </Tooltip>
    );
  }

  if (status) {
    return (
      <span
        className={styles.statusLetter}
        style={STATUS_COLOR_STYLES[status]}
        data-testid={ElementIds.FILE_BROWSER_TREE_ROW_STATUS}
      >
        {status}
      </span>
    );
  }

  return null;
};

export const TreeRow = memo(function TreeRow({
  node,
  depth,
  isExpanded,
  isFocused,
  isActiveFile,
  folderChangeCount,
  addedLines,
  removedLines,
  parentDir,
  onToggleExpand,
  onFileClick,
  onDiscardFile,
}: TreeRowProps): ReactElement {
  const isFolder = node.type === "directory";
  const isDeleted = node.status === "D";
  const { baseName, extension } = splitFileName(node.name);
  const paddingLeft = TREE_ROW_BASE_PADDING_LEFT + depth * TREE_ROW_DEPTH_INDENT;

  const handleClick = (): void => {
    if (isFolder) {
      onToggleExpand(node.path);
    } else {
      onFileClick(node.path);
    }
  };

  return (
    <div
      className={`${styles.row} ${isDeleted ? styles.deleted : ""} ${isFocused ? styles.focused : ""} ${isActiveFile ? styles.activeFile : ""}`}
      style={{ paddingLeft }}
      onClick={handleClick}
      data-testid={ElementIds.FILE_BROWSER_TREE_ROW}
      data-tree-path={node.path}
      role="treeitem"
      aria-expanded={isFolder ? isExpanded : undefined}
    >
      {isFolder ? (
        <FolderIcon isExpanded={isExpanded} />
      ) : (
        <>
          <span className={styles.iconArea} />
          <FileTypeIcon filename={node.name} />
        </>
      )}

      <span className={styles.name}>
        {baseName}
        {extension && <span className={styles.extension}>{extension}</span>}
      </span>

      {parentDir && <span className={styles.flatListDir}>{truncateMiddlePath(parentDir)}</span>}

      <span className={styles.spacer} />

      <LineStats addedLines={addedLines} removedLines={removedLines} />
      <StatusIndicator errorMessage={node.errorMessage} status={node.status} />

      {isFolder && folderChangeCount > 0 && <span className={styles.badge}>{folderChangeCount}</span>}

      {!isFolder && onDiscardFile && (
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.discardButton}
          data-testid={ElementIds.DISCARD_BUTTON}
          onClick={(e) => {
            e.stopPropagation();
            onDiscardFile(node.path);
          }}
          title="Discard changes"
        >
          <X size={12} />
        </IconButton>
      )}
    </div>
  );
});
