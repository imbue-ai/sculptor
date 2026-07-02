import { Select } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useMemo } from "react";

import { ElementIds } from "~/api";
import type { RecentDiffFile } from "~/pages/workspace/components/diffPanel/atoms.ts";
import {
  openCommitDiffTabAtom,
  openFileFromUiEventAtom,
  openFileViewTabAtom,
  recentDiffFilesAtomFamily,
  recordRecentDiffFileAtom,
} from "~/pages/workspace/components/diffPanel/atoms.ts";

import styles from "./FilePathSelect.module.scss";

/**
 * Which panel's recents this header feeds and reads. Each panel keeps its own
 * independent list, and picking an entry stays in that panel: Files re-opens a
 * read-only file view, Changes re-opens the file's diff, and Commits re-opens
 * the file's diff within the commit it was viewed in (hence the hash).
 */
export type RecentFilesScope = { panel: "files" } | { panel: "changes" } | { panel: "commits"; commitHash: string };

type FilePathSelectProps = {
  workspaceId: string;
  filePath: string;
  recentFilesScope: RecentFilesScope;
};

/** Split a workspace-relative path into its dim directory part and file name. */
const splitPath = (filePath: string): { dirParts: Array<string>; fileName: string } => {
  const parts = filePath.split("/");
  return { dirParts: parts.slice(0, -1), fileName: parts[parts.length - 1] };
};

/** A Select item value must be unique per entry: commit entries for the same
 *  path in different commits are distinct, so the hash joins the path. */
const entryValue = (entry: RecentDiffFile): string =>
  entry.commitHash === undefined ? entry.path : `${entry.commitHash}:${entry.path}`;

/**
 * The viewer header's file path, rendered as a ghost Select: the trigger shows
 * the open file's breadcrumb (dim directories, bright name), and opening it
 * lists the files recently viewed IN THIS PANEL. Picking one re-opens it in
 * this panel — a file view in Files, a diff in Changes, and the commit-scoped
 * diff in Commits.
 */
export const FilePathSelect = ({ workspaceId, filePath, recentFilesScope }: FilePathSelectProps): ReactElement => {
  // state and hooks
  const { panel } = recentFilesScope;
  const commitHash = recentFilesScope.panel === "commits" ? recentFilesScope.commitHash : undefined;
  const recentFiles = useAtomValue(recentDiffFilesAtomFamily(workspaceId, panel));
  const recordRecentFile = useSetAtom(recordRecentDiffFileAtom);
  const openDiff = useSetAtom(openFileFromUiEventAtom);
  const openFileView = useSetAtom(openFileViewTabAtom);
  const openCommitDiff = useSetAtom(openCommitDiffTabAtom);

  // effects
  // Every file the header shows counts as "recently viewed" in this panel.
  useEffect(() => {
    recordRecentFile({ workspaceId, panel, entry: { path: filePath, commitHash } });
  }, [workspaceId, panel, filePath, commitHash, recordRecentFile]);

  // functions and callbacks
  const handleValueChange = (value: string): void => {
    const entry = recentFiles.find((candidate) => entryValue(candidate) === value);
    if (entry === undefined) {
      return;
    }

    if (panel === "files") {
      openFileView({ workspaceId, filePath: entry.path });
    } else if (panel === "changes") {
      openDiff({ workspaceId, filePath: entry.path, mode: "diff" });
    } else if (entry.commitHash !== undefined) {
      openCommitDiff({ workspaceId, commitHash: entry.commitHash, filePath: entry.path });
    }
  };

  // JSX and rendering logic
  const { dirParts, fileName } = useMemo(() => splitPath(filePath), [filePath]);
  const currentValue = entryValue({ path: filePath, commitHash });

  return (
    <Select.Root size="1" value={currentValue} onValueChange={handleValueChange}>
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
        {recentFiles.map((entry) => {
          const { dirParts: itemDirParts, fileName: itemFileName } = splitPath(entry.path);
          return (
            <Select.Item key={entryValue(entry)} value={entryValue(entry)}>
              <span className={styles.breadcrumb}>
                {itemDirParts.length > 0 && (
                  <>
                    <span className={styles.segment}>{itemDirParts.join("/")}</span>
                    <span className={styles.separator}>/</span>
                  </>
                )}
                <span className={styles.fileName}>{itemFileName}</span>
                {/* Commit entries can repeat a path across commits; the short
                    hash tells them apart. */}
                {entry.commitHash !== undefined && (
                  <span className={styles.segment}> {entry.commitHash.slice(0, 7)}</span>
                )}
              </span>
            </Select.Item>
          );
        })}
      </Select.Content>
    </Select.Root>
  );
};
