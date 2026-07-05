import { useMemo } from "react";

import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import type { DiffScope } from "~/pages/workspace/diffPanel/types/diffPanel.ts";
import { parseDiff } from "~/pages/workspace/utils/diff.ts";

import type { FileStatus, PerFileDiff } from "./types/fileBrowser.ts";
import { determineFileStatus } from "./utils/fileTree.ts";

/** Selects the appropriate diff string for the given scope. */
const selectDiffString = (
  diff: { uncommittedDiff?: string | null; targetBranchDiff?: string | null } | null,
  scope: DiffScope,
): string | null | undefined => {
  if (!diff) return null;
  return scope === "vs-target-branch" ? diff.targetBranchDiff : diff.uncommittedDiff;
};

/** Parses the workspace diff string once and returns both a status map and a per-file diff map.
 *  Shared between useFileStatusMap and usePerFileDiffMap to avoid parsing the same diff twice. */
const useParsedDiffMaps = (
  workspaceId: string,
  scope: DiffScope,
): { statusMap: Map<string, FileStatus>; perFileDiffMap: Map<string, PerFileDiff> } => {
  const { data: diff } = useWorkspaceDiff(workspaceId);
  const diffString = selectDiffString(diff ?? null, scope);

  return useMemo(() => {
    const statusMap = new Map<string, FileStatus>();
    const perFileDiffMap = new Map<string, PerFileDiff>();
    if (!diffString) {
      return { statusMap, perFileDiffMap };
    }

    const parsed = parseDiff(diffString);
    for (const fileChange of parsed.fileChanges) {
      const { referenceFileName, previousFileName } = fileChange.fileNames;
      const status = determineFileStatus(fileChange);
      statusMap.set(referenceFileName, status);
      perFileDiffMap.set(referenceFileName, {
        filePath: referenceFileName,
        previousFilePath: previousFileName !== referenceFileName ? previousFileName : null,
        status,
        diffString: fileChange.diffString,
        addedLines: fileChange.changes.added,
        removedLines: fileChange.changes.removed,
      });
    }

    return { statusMap, perFileDiffMap };
  }, [diffString]);
};

/** Builds a map from file path to FileStatus by parsing the workspace diff.
 *  When scope is "uncommitted" (default), uses uncommittedDiff (changes since HEAD),
 *  matching the behavior of `git status`.
 *  When scope is "vs-target-branch", uses targetBranchDiff (all changes vs target branch). */
export const useFileStatusMap = (workspaceId: string, scope: DiffScope = "uncommitted"): Map<string, FileStatus> => {
  return useParsedDiffMaps(workspaceId, scope).statusMap;
};

/** Builds a map from file path to per-file diff data (status, line counts, previous path).
 *  Uses the same scope as useFileStatusMap for consistency. */
export const usePerFileDiffMap = (workspaceId: string, scope: DiffScope = "uncommitted"): Map<string, PerFileDiff> => {
  return useParsedDiffMaps(workspaceId, scope).perFileDiffMap;
};
