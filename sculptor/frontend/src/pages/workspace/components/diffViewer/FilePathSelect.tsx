import { Select } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useMemo } from "react";

import { ElementIds } from "~/api";
import {
  openFileFromUiEventAtom,
  recentDiffFilesAtomFamily,
  recordRecentDiffFileAtom,
} from "~/pages/workspace/components/diffPanel/atoms.ts";

import styles from "./FilePathSelect.module.scss";

type FilePathSelectProps = {
  workspaceId: string;
  filePath: string;
};

/** Split a workspace-relative path into its dim directory part and file name. */
const splitPath = (filePath: string): { dirParts: Array<string>; fileName: string } => {
  const parts = filePath.split("/");
  return { dirParts: parts.slice(0, -1), fileName: parts[parts.length - 1] };
};

/**
 * The viewer header's file path, rendered as a ghost Select: the trigger shows
 * the open file's breadcrumb (dim directories, bright name), and opening it
 * lists the ten most recently viewed files in this workspace. Picking one
 * re-opens it — as a diff when it has uncommitted changes, else as a read-only
 * file view (the same "auto" resolution agent-opened files use).
 */
export const FilePathSelect = ({ workspaceId, filePath }: FilePathSelectProps): ReactElement => {
  // state and hooks
  const recentFiles = useAtomValue(recentDiffFilesAtomFamily(workspaceId));
  const recordRecentFile = useSetAtom(recordRecentDiffFileAtom);
  const openFile = useSetAtom(openFileFromUiEventAtom);

  // effects
  // Every file the header shows counts as "recently viewed".
  useEffect(() => {
    recordRecentFile({ workspaceId, filePath });
  }, [workspaceId, filePath, recordRecentFile]);

  // functions and callbacks
  const handleValueChange = (path: string): void => {
    openFile({ workspaceId, filePath: path, mode: "auto" });
  };

  // JSX and rendering logic
  const { dirParts, fileName } = useMemo(() => splitPath(filePath), [filePath]);

  return (
    <Select.Root size="1" value={filePath} onValueChange={handleValueChange}>
      <Select.Trigger
        variant="ghost"
        color="gray"
        className={styles.trigger}
        data-testid={ElementIds.DIFF_FILE_PATH_SELECT}
      >
        <span className={styles.breadcrumb}>
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
        </span>
      </Select.Trigger>
      <Select.Content position="popper">
        {recentFiles.map((path) => {
          const { dirParts: itemDirParts, fileName: itemFileName } = splitPath(path);
          return (
            <Select.Item key={path} value={path}>
              <span className={styles.breadcrumb}>
                {itemDirParts.length > 0 && (
                  <>
                    <span className={styles.segment}>{itemDirParts.join("/")}</span>
                    <span className={styles.separator}>/</span>
                  </>
                )}
                <span className={styles.fileName}>{itemFileName}</span>
              </span>
            </Select.Item>
          );
        })}
      </Select.Content>
    </Select.Root>
  );
};
