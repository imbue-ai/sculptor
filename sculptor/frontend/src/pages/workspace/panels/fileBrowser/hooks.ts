import { useCallback, useMemo } from "react";

import { workspaceOpenInOs } from "~/api";
import { useForceRefreshWorkspaceDiff, useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import { useWorkspaceFiles } from "~/common/state/hooks/useWorkspaceFiles.ts";
import { parseDiff } from "~/components/DiffUtils.ts";
import type { DiffScope } from "~/pages/workspace/components/diffPanel/types.ts";

import type { FileStatus, FlatFileEntry, PerFileDiff, TreeNode } from "./types.ts";
import { buildFileTree, computeFolderChangeCounts, determineFileStatus, filterFilesBySubstring } from "./utils.ts";

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

type UseFileTreeResult = {
  tree: Array<TreeNode>;
  folderChangeCounts: Map<string, number>;
  /** True while we don't have file list data to show yet. */
  isPending: boolean;
  /** True while a diff fetch is in flight (initial or background refresh). */
  isFetching: boolean;
  /** True while the backend is recomputing the diff (`diff_status` is GENERATING). */
  isGenerating: boolean;
  refetch: () => void;
};

/** Builds the file tree and folder change counts from the workspace file list and diff. */
export const useFileTree = (workspaceId: string, scope: DiffScope = "uncommitted"): UseFileTreeResult => {
  const { data: files, isPending, isFetching: isFilesFetching, refetch: refetchFiles } = useWorkspaceFiles(workspaceId);
  const statusMap = useFileStatusMap(workspaceId, scope);
  const { data: diff, isFetching: isDiffFetching, isGenerating } = useWorkspaceDiff(workspaceId);
  const refreshDiff = useForceRefreshWorkspaceDiff(workspaceId);
  const fileErrors = useMemo(() => diff?.fileErrors ?? {}, [diff?.fileErrors]);
  const isFetching = isFilesFetching || isDiffFetching;

  const tree = useMemo(() => {
    if (!files) {
      return [];
    }

    const builtTree = buildFileTree({ files, fileStatusMap: statusMap, fileErrors });

    // Add deleted files from the diff that don't appear in the file list
    const existingPaths = new Set(files.map((f) => f.path));
    for (const [filePath, status] of statusMap) {
      if (status === "D" && !existingPaths.has(filePath)) {
        addDeletedFileToTree({ tree: builtTree, filePath, fileErrors });
      }
    }

    return builtTree;
  }, [files, statusMap, fileErrors]);

  const folderChangeCounts = useMemo(() => computeFolderChangeCounts(tree), [tree]);

  // Combined refetch: refresh both the file list and the diff so the
  // Uncommitted tab reflects external changes (e.g. files created via terminal).
  const refetch = useCallback(() => {
    refetchFiles();
    void refreshDiff();
  }, [refetchFiles, refreshDiff]);

  return { tree, folderChangeCounts, isPending, isFetching, isGenerating, refetch };
};

const addDeletedFileToTree = ({
  tree,
  filePath,
  fileErrors,
}: {
  tree: Array<TreeNode>;
  filePath: string;
  fileErrors: Record<string, string>;
}): void => {
  const segments = filePath.split("/");
  const fileName = segments[segments.length - 1];

  if (segments.length === 1) {
    if (tree.some((n) => n.path === filePath)) {
      return;
    }
    tree.push({
      name: fileName,
      path: filePath,
      type: "file",
      children: [],
      status: "D",
      errorMessage: fileErrors[filePath],
    });
    return;
  }

  let currentLevel = tree;
  for (let i = 0; i < segments.length - 1; i++) {
    const folderName = segments[i];
    const baseFolderPath = segments.slice(0, i + 1).join("/");
    // If a non-directory node (e.g. a symlink that replaced the directory)
    // already occupies the path we'd use for the synthesized folder, fall
    // back to a disambiguated path with a trailing slash so the React key
    // doesn't collide with the file at the same path.
    const hasConflict = currentLevel.some((n) => n.path === baseFolderPath && n.type !== "directory");
    const folderPath = hasConflict ? `${baseFolderPath}/` : baseFolderPath;
    const displayName = hasConflict ? `${folderName}/` : folderName;
    let folder = currentLevel.find((n) => n.path === folderPath && n.type === "directory");
    if (!folder) {
      folder = {
        name: displayName,
        path: folderPath,
        type: "directory",
        children: [],
      };
      currentLevel.push(folder);
    }
    currentLevel = folder.children;
  }

  if (currentLevel.some((n) => n.path === filePath)) {
    return;
  }
  currentLevel.push({
    name: fileName,
    path: filePath,
    type: "file",
    children: [],
    status: "D",
    errorMessage: fileErrors[filePath],
  });
};

const EMPTY_MATCHING_PATHS = new Set<string>();

type UseFileSearchResult = {
  results: Array<FlatFileEntry>;
  resultCount: number;
  matchingPaths: Set<string>;
};

/** Searches workspace files by case-insensitive substring match on file path. */
export const useFileSearch = (workspaceId: string, query: string): UseFileSearchResult => {
  const { data: files } = useWorkspaceFiles(workspaceId);

  return useMemo(() => {
    if (!files || query === "") {
      return { results: [], resultCount: 0, matchingPaths: EMPTY_MATCHING_PATHS };
    }
    return filterFilesBySubstring(files, query);
  }, [files, query]);
};

export const openInOs = async ({
  workspaceId,
  path,
  action,
}: {
  workspaceId: string;
  path: string;
  action: "open_file" | "open_containing_folder";
}): Promise<void> => {
  try {
    await workspaceOpenInOs({
      path: { workspace_id: workspaceId },
      body: { path, action },
    });
  } catch (error) {
    console.error("Error opening in OS:", error);
  }
};
