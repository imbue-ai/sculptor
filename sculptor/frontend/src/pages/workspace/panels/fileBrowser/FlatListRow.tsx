import { IconButton } from "@radix-ui/themes";
import { X } from "lucide-react";
import { memo, type ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./FileTree.module.scss";
import type { FlatFileEntry } from "./types.ts";
import { STATUS_COLOR_STYLES, truncateMiddlePath } from "./utils.ts";

type FlatListRowProps = {
  entry: FlatFileEntry;
  isFocused: boolean;
  /** True when this row is the file selected in an embedding panel's viewer. */
  isSelected?: boolean;
  addedLines?: number;
  removedLines?: number;
  onFileClick: (path: string) => void;
  onDiscardFile?: (filePath: string) => void;
};

export const FlatListRow = memo(function FlatListRow({
  entry,
  isFocused,
  isSelected,
  addedLines,
  removedLines,
  onFileClick,
  onDiscardFile,
}: FlatListRowProps): ReactElement {
  const isDeleted = entry.status === "D";

  const handleClick = (): void => {
    onFileClick(entry.path);
  };

  return (
    <div
      className={`${styles.flatListRow} ${isDeleted ? styles.deleted : ""} ${isFocused ? styles.focused : ""} ${isSelected ? styles.activeFile : ""}`}
      onClick={handleClick}
    >
      <span className={styles.flatListName}>{entry.name}</span>
      {entry.parentPath && <span className={styles.flatListDir}>{truncateMiddlePath(entry.parentPath)}</span>}

      <span className={styles.spacer} />

      {(addedLines != null && addedLines > 0) || (removedLines != null && removedLines > 0) ? (
        <span className={styles.lineStats}>
          {addedLines != null && addedLines > 0 && <span className={styles.lineStatsAdded}>+{addedLines}</span>}
          {removedLines != null && removedLines > 0 && <span className={styles.lineStatsRemoved}>-{removedLines}</span>}
        </span>
      ) : null}

      {entry.status && (
        <span className={styles.statusLetter} style={STATUS_COLOR_STYLES[entry.status]}>
          {entry.status}
        </span>
      )}

      {onDiscardFile && (
        <IconButton
          variant="ghost"
          size="1"
          color="gray"
          className={styles.discardButton}
          data-testid={ElementIds.DISCARD_BUTTON}
          onClick={(e) => {
            e.stopPropagation();
            onDiscardFile(entry.path);
          }}
          title="Discard changes"
        >
          <X size={12} />
        </IconButton>
      )}
    </div>
  );
});
