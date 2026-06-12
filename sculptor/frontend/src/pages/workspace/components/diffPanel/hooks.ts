import { useAtomValue } from "jotai";
import { useMemo } from "react";

import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import type { DiffData } from "~/components/DiffUtils.ts";
import { getLineCounts, parseDiff } from "~/components/DiffUtils.ts";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types.ts";
import { determineFileStatus, isBinaryFile } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import { diffPanelStateAtomFamily } from "./atoms.ts";
import type { SingleFileDiffTab } from "./types.ts";
import { isCombinedTab, isCommitDiffTab, isFileViewTab, TARGET_BRANCH_DIFF_PREFIX } from "./types.ts";

type ActiveFileDiffResult = {
  filePath: string | null;
  /** The tab identifier (may include a scope prefix). Used for tab close operations. */
  tabFilePath: string | null;
  previousFilePath: string | null;
  status: FileStatus | null;
  diffString: string | null;
  addedLines: number;
  removedLines: number;
  isBinary: boolean;
  isCombined: boolean;
  isFileView: boolean;
  isCommitDiff: boolean;
  /** True when the active tab shows a vs-target-branch diff (the "All" scope). */
  isTargetBranchDiff: boolean;
  /**
   * Commit SHA of merge-base(target, HEAD) — the ref the vs-target-branch
   * diff's old-side line numbers reference. Used as the base ref for old-side
   * file content so hunk expansion stays in sync with the diff. Null when there
   * is no target branch / merge-base.
   */
  targetBranchMergeBase: string | null;
  /** True while a workspace-diff fetch is in flight. */
  isFetching: boolean;
  commitHash: string | null;
  errorMessage: string | null;
};

const EMPTY_RESULT: Omit<ActiveFileDiffResult, "isFetching" | "targetBranchMergeBase"> = {
  filePath: null,
  tabFilePath: null,
  previousFilePath: null,
  status: null,
  diffString: null,
  addedLines: 0,
  removedLines: 0,
  isBinary: false,
  isCombined: false,
  isFileView: false,
  isCommitDiff: false,
  isTargetBranchDiff: false,
  commitHash: null,
  errorMessage: null,
};

export const useActiveFileDiff = (workspaceId: string): ActiveFileDiffResult => {
  const diffPanelState = useAtomValue(diffPanelStateAtomFamily(workspaceId));
  const { data: diff, isFetching } = useWorkspaceDiff(workspaceId);

  const parsedUncommittedDiff = useMemo((): DiffData | null => {
    if (!diff?.uncommittedDiff) return null;
    return parseDiff(diff.uncommittedDiff);
  }, [diff?.uncommittedDiff]);

  const parsedTargetBranchDiff = useMemo((): DiffData | null => {
    if (!diff?.targetBranchDiff) return null;
    return parseDiff(diff.targetBranchDiff);
  }, [diff?.targetBranchDiff]);

  // Compute the static parts of the result inside the memo; merge `isFetching`
  // and `targetBranchMergeBase` outside so changes to those don't invalidate
  // the memo's structure.
  const memoized = useMemo((): Omit<ActiveFileDiffResult, "isFetching" | "targetBranchMergeBase"> => {
    const { activeTabPath, openTabs } = diffPanelState;
    if (!activeTabPath) return EMPTY_RESULT;

    const activeTab = openTabs.find((t) => t.filePath === activeTabPath);
    if (!activeTab) return EMPTY_RESULT;

    // Combined review tab — DiffPanel renders CombinedDiffView for this case
    if (isCombinedTab(activeTab)) {
      return { ...EMPTY_RESULT, filePath: activeTabPath, tabFilePath: activeTabPath, isCombined: true };
    }

    // File view tab — DiffPanel renders ReadOnlyPreview for this case
    if (isFileViewTab(activeTab)) {
      return { ...EMPTY_RESULT, filePath: activeTab.realPath, tabFilePath: activeTabPath, isFileView: true };
    }

    // Commit diff tab — DiffPanel fetches from commit-diff endpoint
    if (isCommitDiffTab(activeTab)) {
      return {
        ...EMPTY_RESULT,
        filePath: activeTab.realPath,
        tabFilePath: activeTabPath,
        isCommitDiff: true,
        commitHash: activeTab.commitHash,
      };
    }

    const tabScope = (activeTab as SingleFileDiffTab).scope;

    // If the tab was opened with a specific diff string (e.g., from chip popover),
    // use it directly instead of looking up from workspace uncommitted changes.
    if ((activeTab as SingleFileDiffTab).diffString) {
      const lineCounts = getLineCounts((activeTab as SingleFileDiffTab).diffString!);

      return {
        filePath: activeTabPath,
        tabFilePath: activeTabPath,
        previousFilePath: null,
        status: activeTab.status,
        diffString: (activeTab as SingleFileDiffTab).diffString!,
        addedLines: lineCounts.added,
        removedLines: lineCounts.removed,
        isBinary: false,
        isCombined: false,
        isFileView: false,
        isCommitDiff: false,
        isTargetBranchDiff: tabScope === "vs-target-branch",
        commitHash: null,
        errorMessage: null,
      };
    }

    const parsedDiff = tabScope === "vs-target-branch" ? parsedTargetBranchDiff : parsedUncommittedDiff;

    // Strip the scope prefix to get the real file path for lookups.
    const realPath = activeTabPath.startsWith(TARGET_BRANCH_DIFF_PREFIX)
      ? activeTabPath.slice(TARGET_BRANCH_DIFF_PREFIX.length)
      : activeTabPath;

    const fileName = realPath.split("/").pop() ?? realPath;
    const isBinary = isBinaryFile(fileName);

    const errorMessage = diff?.fileErrors?.[realPath] ?? null;

    if (!parsedDiff) {
      return {
        ...EMPTY_RESULT,
        filePath: realPath,
        tabFilePath: activeTabPath,
        status: activeTab.status,
        isBinary,
        errorMessage,
      };
    }

    const fileChange = parsedDiff.fileChanges.find((fc) => fc.fileNames.referenceFileName === realPath);

    if (!fileChange) {
      return {
        ...EMPTY_RESULT,
        filePath: realPath,
        tabFilePath: activeTabPath,
        status: activeTab.status,
        isBinary,
        errorMessage,
      };
    }

    const previousFilePath =
      fileChange.fileNames.previousFileName !== realPath ? fileChange.fileNames.previousFileName : null;

    // Derive status from diff data rather than stored tab status, which may be stale
    const status: FileStatus = determineFileStatus(fileChange);

    return {
      filePath: realPath,
      tabFilePath: activeTabPath,
      previousFilePath,
      status,
      diffString: fileChange.diffString,
      addedLines: fileChange.changes.added,
      removedLines: fileChange.changes.removed,
      isBinary,
      isCombined: false,
      isFileView: false,
      isCommitDiff: false,
      isTargetBranchDiff: tabScope === "vs-target-branch",
      commitHash: null,
      errorMessage,
    };
  }, [diffPanelState, parsedUncommittedDiff, parsedTargetBranchDiff, diff?.fileErrors]);

  return { ...memoized, isFetching, targetBranchMergeBase: diff?.targetBranchMergeBase || null };
};
