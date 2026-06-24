import { useMemo } from "react";

import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import type { DiffData } from "~/components/DiffUtils.ts";
import { getLineCounts, parseDiff } from "~/components/DiffUtils.ts";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { determineFileStatus, isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import type { DiffSelection } from "./types.ts";

/**
 * The resolved content the {@link DiffViewer} renders for the current
 * selection. Mirrors the shape the old in-panel viewer derived from the global
 * diff-tab atom, but is driven entirely by the per-instance `selection` prop so
 * each embedded viewer is independent (no shared "active diff" singleton).
 */
export type DiffViewerContent = {
  filePath: string | null;
  /** The tab identifier (may carry a scope prefix); used for file-actions. */
  tabFilePath: string | null;
  previousFilePath: string | null;
  status: FileStatus | null;
  diffString: string | null;
  addedLines: number;
  removedLines: number;
  isBinary: boolean;
  isFileView: boolean;
  isCommitDiff: boolean;
  /** True when the selection diffs against the target branch (the "All" scope). */
  isTargetBranchDiff: boolean;
  /**
   * Commit SHA of merge-base(target, HEAD) — the ref the vs-target-branch
   * diff's old-side line numbers reference. Used as the base ref for old-side
   * file content so hunk expansion stays in sync. Null when there is no
   * target branch / merge-base.
   */
  targetBranchMergeBase: string | null;
  /** True while a workspace-diff fetch is in flight. */
  isFetching: boolean;
  commitHash: string | null;
  errorMessage: string | null;
};

const EMPTY_CONTENT: Omit<DiffViewerContent, "isFetching" | "targetBranchMergeBase"> = {
  filePath: null,
  tabFilePath: null,
  previousFilePath: null,
  status: null,
  diffString: null,
  addedLines: 0,
  removedLines: 0,
  isBinary: false,
  isFileView: false,
  isCommitDiff: false,
  isTargetBranchDiff: false,
  commitHash: null,
  errorMessage: null,
};

/**
 * Resolve a {@link DiffSelection} into the content the viewer renders. Reuses
 * the same workspace-diff parsing the in-panel viewer relied on, so the diff
 * content behavior (status derivation, rename detection, target-branch scope,
 * error surfacing) is preserved — only the source of the selection changes from
 * a global atom to a prop.
 */
export const useDiffViewerContent = (workspaceId: string, selection: DiffSelection | null): DiffViewerContent => {
  const { data: diff, isFetching } = useWorkspaceDiff(workspaceId);

  const parsedUncommittedDiff = useMemo((): DiffData | null => {
    if (!diff?.uncommittedDiff) return null;
    return parseDiff(diff.uncommittedDiff);
  }, [diff?.uncommittedDiff]);

  const parsedTargetBranchDiff = useMemo((): DiffData | null => {
    if (!diff?.targetBranchDiff) return null;
    return parseDiff(diff.targetBranchDiff);
  }, [diff?.targetBranchDiff]);

  const memoized = useMemo((): Omit<DiffViewerContent, "isFetching" | "targetBranchMergeBase"> => {
    if (!selection) return EMPTY_CONTENT;

    if (selection.kind === "file-view") {
      return {
        ...EMPTY_CONTENT,
        filePath: selection.filePath,
        tabFilePath: selection.tabFilePath ?? selection.filePath,
        isFileView: true,
      };
    }

    if (selection.kind === "commit-diff") {
      return {
        ...EMPTY_CONTENT,
        filePath: selection.filePath,
        tabFilePath: selection.tabFilePath ?? selection.filePath,
        isCommitDiff: true,
        commitHash: selection.commitHash,
      };
    }

    const { filePath, scope, diffString: explicitDiffString, status, tabFilePath } = selection;
    const isTargetBranchDiff = scope === "vs-target-branch";

    // Explicit diff string (e.g. from a chip popover): render it directly
    // instead of looking it up from the workspace diff.
    if (explicitDiffString) {
      const lineCounts = getLineCounts(explicitDiffString);
      return {
        ...EMPTY_CONTENT,
        filePath,
        tabFilePath: tabFilePath ?? filePath,
        status,
        diffString: explicitDiffString,
        addedLines: lineCounts.added,
        removedLines: lineCounts.removed,
        isTargetBranchDiff,
      };
    }

    const parsedDiff = isTargetBranchDiff ? parsedTargetBranchDiff : parsedUncommittedDiff;
    const fileName = filePath.split("/").pop() ?? filePath;
    const isBinary = isBinaryFile(fileName);
    const errorMessage = diff?.fileErrors?.[filePath] ?? null;

    if (!parsedDiff) {
      return { ...EMPTY_CONTENT, filePath, tabFilePath: tabFilePath ?? filePath, status, isBinary, errorMessage };
    }

    const fileChange = parsedDiff.fileChanges.find((fc) => fc.fileNames.referenceFileName === filePath);
    if (!fileChange) {
      return { ...EMPTY_CONTENT, filePath, tabFilePath: tabFilePath ?? filePath, status, isBinary, errorMessage };
    }

    const previousFilePath =
      fileChange.fileNames.previousFileName !== filePath ? fileChange.fileNames.previousFileName : null;
    // Derive status from diff data rather than the passed-in value, which may be stale.
    const derivedStatus: FileStatus = determineFileStatus(fileChange);

    return {
      ...EMPTY_CONTENT,
      filePath,
      tabFilePath: tabFilePath ?? filePath,
      previousFilePath,
      status: derivedStatus,
      diffString: fileChange.diffString,
      addedLines: fileChange.changes.added,
      removedLines: fileChange.changes.removed,
      isBinary,
      isTargetBranchDiff,
      errorMessage,
    };
  }, [selection, parsedUncommittedDiff, parsedTargetBranchDiff, diff?.fileErrors]);

  return { ...memoized, isFetching, targetBranchMergeBase: diff?.targetBranchMergeBase ?? null };
};
