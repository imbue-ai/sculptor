import { useMemo } from "react";

import { useWorkspaceFileContent } from "~/common/state/hooks/useWorkspaceFileContent.ts";
import type { FileStatus } from "~/pages/workspace/panels/fileBrowser/types/fileBrowser.ts";

/**
 * Pierre expects lines split so each element retains its trailing newline.
 * E.g. `"a\nb\n"` → `["a\n", "b\n"]`
 */
const SPLIT_WITH_NEWLINES = /(?<=\n)/;

type FileLines = {
  oldLines: Array<string> | undefined;
  newLines: Array<string> | undefined;
};

const splitContentIntoLines = (content: string | undefined): Array<string> | undefined =>
  content != null ? content.split(SPLIT_WITH_NEWLINES) : undefined;

/**
 * Fetches the old (at `baseCommitId`) and new (working-directory) full file
 * content for a single file so Pierre can render expandable hunk separators.
 *
 * `baseCommitId` is the commit the diff was taken against, as the backend named
 * it; null means the diff has no single base, so no old content is fetched.
 * Skips fetching when the file status makes one side unnecessary (e.g. new
 * files have no old content; deleted files have no new content). Routes
 * through `useWorkspaceFileContent`, which keys by `(workspaceId, filePath,
 * gitRef)` — so multiple components rendering the same file (e.g. the diff
 * panel + a combined diff entry for the same file) share one fetch, and
 * navigating away and back to the same file is a cache hit.
 */
export const useFileLines = (
  workspaceId: string,
  filePath: string | null,
  previousFilePath: string | null,
  fileStatus: FileStatus | null,
  baseCommitId: string | null,
): FileLines => {
  const isNewFile = fileStatus === "A";
  const isDeletedFile = fileStatus === "D";
  const isOldContentWanted = !isNewFile && filePath !== null && baseCommitId !== null;

  const { data: oldContent } = useWorkspaceFileContent(
    isOldContentWanted ? workspaceId : null,
    isOldContentWanted ? (previousFilePath ?? filePath) : null,
    baseCommitId,
  );

  // New content — skip for deleted files
  const { data: newContent } = useWorkspaceFileContent(
    isDeletedFile || !filePath ? null : workspaceId,
    isDeletedFile ? null : filePath,
    null,
  );

  return useMemo(
    () => ({
      oldLines: splitContentIntoLines(oldContent),
      newLines: splitContentIntoLines(newContent),
    }),
    [oldContent, newContent],
  );
};
