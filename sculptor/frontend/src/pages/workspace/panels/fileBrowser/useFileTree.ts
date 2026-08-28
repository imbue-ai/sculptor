import { useCallback, useMemo } from "react";

import { useForceRefreshWorkspaceDiff, useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import { useWorkspaceFiles } from "~/common/state/hooks/useWorkspaceFiles.ts";
import type { DiffScope } from "~/pages/workspace/diffPanel/types/diffPanel.ts";

import { useFileStatusMap } from "./fileDiffMaps.ts";
import type { TreeNode } from "./types/fileBrowser.ts";
import { buildFileTree, computeFolderChangeCounts } from "./utils/fileTree.ts";

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
