import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { TreeRow } from "~/pages/workspace/panels/fileBrowser/TreeRow.tsx";
import type { FileStatus, TreeNode, ViewMode } from "~/pages/workspace/panels/fileBrowser/types.ts";
import {
  collectAllFolderPaths,
  compactSingleChildFolders,
  computeFolderChangeCounts,
  flattenVisibleTreeWithDepth,
  sortTreeNodes,
} from "~/pages/workspace/panels/fileBrowser/utils.ts";

type HistoryFile = {
  path: string;
  status: FileStatus;
  additions?: number;
  deletions?: number;
};

type HistoryFileListProps = {
  files: Array<HistoryFile>;
  viewMode: ViewMode;
  onFileClick: (filePath: string, status: FileStatus) => void;
};

/** Build a tree of TreeNode from a flat list of file paths + statuses. */
const buildTreeFromFiles = (files: Array<HistoryFile>): Array<TreeNode> => {
  const root: Array<TreeNode> = [];
  const dirMap = new Map<string, TreeNode>();

  const getOrCreateDir = (dirPath: string): TreeNode => {
    const existing = dirMap.get(dirPath);
    if (existing) return existing;

    const parts = dirPath.split("/");
    const name = parts[parts.length - 1];
    const node: TreeNode = { name, path: dirPath, type: "directory", children: [] };
    dirMap.set(dirPath, node);

    if (parts.length === 1) {
      root.push(node);
    } else {
      const parentPath = parts.slice(0, -1).join("/");
      const parent = getOrCreateDir(parentPath);
      parent.children.push(node);
    }
    return node;
  };

  for (const file of files) {
    const parts = file.path.split("/");
    const name = parts[parts.length - 1];
    const fileNode: TreeNode = { name, path: file.path, type: "file", children: [], status: file.status };

    if (parts.length === 1) {
      root.push(fileNode);
    } else {
      const parentPath = parts.slice(0, -1).join("/");
      const parent = getOrCreateDir(parentPath);
      parent.children.push(fileNode);
    }
  }

  return root;
};

/** Sort files by parent directory then by filename (matching Changes tab order). */
const sortHistoryFiles = (files: Array<HistoryFile>): Array<HistoryFile> => {
  const getParentDir = (path: string): string => {
    const lastSlash = path.lastIndexOf("/");
    return lastSlash >= 0 ? path.slice(0, lastSlash) : "";
  };
  return [...files].sort((a, b) => {
    const dirCmp = getParentDir(a.path).localeCompare(getParentDir(b.path));
    if (dirCmp !== 0) return dirCmp;
    const nameA = a.path.slice(a.path.lastIndexOf("/") + 1);
    const nameB = b.path.slice(b.path.lastIndexOf("/") + 1);
    return nameA.toLowerCase().localeCompare(nameB.toLowerCase());
  });
};

/** Convert files to flat TreeNode list (no folders, depth 0) for flat view. */
const toFlatTreeNodes = (files: Array<HistoryFile>): Array<TreeNode> =>
  sortHistoryFiles(files).map((f) => {
    const lastSlash = f.path.lastIndexOf("/");
    return {
      name: lastSlash >= 0 ? f.path.slice(lastSlash + 1) : f.path,
      path: f.path,
      type: "file" as const,
      children: [],
      status: f.status,
    };
  });

export const HistoryFileList = ({ files, viewMode, onFileClick }: HistoryFileListProps): ReactElement => {
  const tree = useMemo(() => {
    const raw = buildTreeFromFiles(files);
    const sorted = sortTreeNodes(raw);
    return compactSingleChildFolders(sorted);
  }, [files]);

  const allFolderPaths = useMemo(() => collectAllFolderPaths(tree), [tree]);

  // Reset expanded folders when the tree changes (all expanded by default).
  // Uses during-render state adjustment instead of useEffect to avoid a
  // stale intermediate render with collapsed folders.
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => new Set(allFolderPaths));
  const [prevAllFolderPaths, setPrevAllFolderPaths] = useState(allFolderPaths);
  if (allFolderPaths !== prevAllFolderPaths) {
    setPrevAllFolderPaths(allFolderPaths);
    setExpandedFolders(new Set(allFolderPaths));
  }

  const folderChangeCounts = useMemo(() => computeFolderChangeCounts(tree), [tree]);

  const flatRows = useMemo(
    () => flattenVisibleTreeWithDepth({ roots: tree, expandedFolders }),
    [tree, expandedFolders],
  );

  const fileMap = useMemo(() => new Map(files.map((f) => [f.path, f])), [files]);
  const flatNodes = useMemo(() => toFlatTreeNodes(files), [files]);

  const handleToggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleFileClick = useCallback(
    (path: string) => {
      const file = fileMap.get(path);
      if (file) {
        onFileClick(path, file.status);
      }
    },
    [fileMap, onFileClick],
  );

  const isFlat = viewMode === "flat";
  const flatNodeRows = useMemo(() => flatNodes.map((node) => ({ node, depth: 0 })), [flatNodes]);
  const rows = isFlat ? flatNodeRows : flatRows;

  return (
    <Flex direction="column" flexGrow="1" gap="0">
      {rows.map(({ node, depth }) => {
        const file = node.type === "file" ? fileMap.get(node.path) : undefined;
        const lastSlash = node.path.lastIndexOf("/");
        const parentDir = isFlat && lastSlash > 0 ? node.path.slice(0, lastSlash) : undefined;
        return (
          <TreeRow
            key={node.path}
            node={node}
            depth={depth}
            isExpanded={expandedFolders.has(node.path)}
            isFocused={false}
            isActiveFile={false}
            folderChangeCount={folderChangeCounts.get(node.path) ?? 0}
            addedLines={file?.additions}
            removedLines={file?.deletions}
            parentDir={parentDir}
            onToggleExpand={handleToggleFolder}
            onFileClick={handleFileClick}
          />
        );
      })}
    </Flex>
  );
};
