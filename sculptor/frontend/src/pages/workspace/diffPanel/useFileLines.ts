import { useMemo } from "react";

import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
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

/**
 * Determine the base git ref for the "old" side of a diff.
 * The target (base) branch is preferred because the "old" content should come
 * from the branch we're diffing against.  Falls back to the source branch or
 * "main" when neither is available.
 */
const getBaseRef = (targetBranch: string | undefined, sourceBranch: string | undefined): string => {
  if (targetBranch) {
    return targetBranch;
  }

  if (sourceBranch) {
    return sourceBranch;
  }
  return "main";
};

const splitContentIntoLines = (content: string | undefined): Array<string> | undefined =>
  content != null ? content.split(SPLIT_WITH_NEWLINES) : undefined;

/**
 * Fetches the old (base-ref) and new (working-directory) full file content for
 * a single file so Pierre can render expandable hunk separators.
 *
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
  baseRefOverride?: string,
): FileLines => {
  const workspace = useWorkspace(workspaceId);
  const baseRef =
    baseRefOverride ?? getBaseRef(workspace?.targetBranch ?? undefined, workspace?.sourceBranch ?? undefined);

  const isNewFile = fileStatus === "A";
  const isDeletedFile = fileStatus === "D";

  // Old content — skip for new files
  const { data: oldContent } = useWorkspaceFileContent(
    isNewFile || !filePath ? null : workspaceId,
    isNewFile ? null : (previousFilePath ?? filePath),
    baseRef,
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
