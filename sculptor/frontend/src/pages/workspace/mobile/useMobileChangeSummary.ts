import { useMemo } from "react";

import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import { parseDiff } from "~/components/DiffUtils.ts";

export type MobileFileStatus = "M" | "A" | "D";

export type MobileFileChange = {
  status: MobileFileStatus;
  /** Basename for the row title. */
  fileName: string;
  /** Directory portion for the row subtitle. */
  dirPath: string;
  added: number;
  removed: number;
};

export type MobileChangeSummary = {
  hasChanges: boolean;
  filesChanged: number;
  added: number;
  removed: number;
  files: ReadonlyArray<MobileFileChange>;
};

const EMPTY: MobileChangeSummary = { hasChanges: false, filesChanged: 0, added: 0, removed: 0, files: [] };

function splitPath(path: string): { fileName: string; dirPath: string } {
  const idx = path.lastIndexOf("/");
  if (idx === -1) return { fileName: path, dirPath: "" };
  return { fileName: path.slice(idx + 1), dirPath: path.slice(0, idx + 1) };
}

/**
 * Shared change summary for the mobile shell — the changes pill, the ⋮ menu's
 * "Review all changes (N files)" count, and the review-all header stats all
 * read from this. Uses the same `uncommitted` scope and `parseDiff` the desktop
 * `CombinedDiffView` defaults to, so the numbers agree.
 */
export const useMobileChangeSummary = (workspaceID: string): MobileChangeSummary => {
  const { data: diff } = useWorkspaceDiff(workspaceID);
  const uncommittedDiff = diff?.uncommittedDiff;

  return useMemo(() => {
    if (!uncommittedDiff) return EMPTY;
    const parsed = parseDiff(uncommittedDiff);
    const files: Array<MobileFileChange> = parsed.fileChanges.map((fc) => {
      const { previousFileName, newFileName, referenceFileName } = fc.fileNames;
      const status: MobileFileStatus = previousFileName === null ? "A" : newFileName === null ? "D" : "M";
      const { fileName, dirPath } = splitPath(referenceFileName);
      return { status, fileName, dirPath, added: fc.changes.added, removed: fc.changes.removed };
    });
    return {
      hasChanges: files.length > 0,
      filesChanged: parsed.changeStats.filesChanged,
      added: parsed.changeStats.added,
      removed: parsed.changeStats.removed,
      files,
    };
  }, [uncommittedDiff]);
};
