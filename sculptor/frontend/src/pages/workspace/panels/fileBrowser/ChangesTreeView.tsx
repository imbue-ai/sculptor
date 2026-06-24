import { Flex, Spinner, Text } from "@radix-ui/themes";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useAtom, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef } from "react";

import { DiffStatus, ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import { openDiffTabAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import type { DiffScope } from "~/pages/workspace/components/diffPanel/types.ts";

import { expandChangesFoldersAtom, fileBrowserStateAtomFamily, toggleChangesFolderAtom } from "./atoms.ts";
import { FileContextMenu } from "./FileContextMenu.tsx";
import styles from "./FileTree.module.scss";
import { FlatListRow } from "./FlatListRow.tsx";
import { useFileTree, usePerFileDiffMap } from "./hooks.ts";
import { TreeRow } from "./TreeRow.tsx";
import type { FileStatus, TreeNode, ViewMode } from "./types.ts";
import { useActiveFileOperation } from "./useActiveFileOperation.ts";
import { useKeyboardNavigation } from "./useKeyboardNavigation.ts";
import { useAgentFileTracking, useCollapseChildren, useTreeNodeMap } from "./useTreeView.ts";
import {
  buildChangesTree,
  collectAllFolderPaths,
  collectDescendantFolderPaths,
  compactSingleChildFolders,
  computeFolderChangeCounts,
  FILE_TREE_OVERSCAN,
  FILE_TREE_PADDING_TOP,
  FILE_TREE_ROW_HEIGHT,
  filterTreeByPaths,
  flattenVisibleTreeWithDepth,
  getChangedFiles,
  isBinaryFile,
} from "./utils.ts";

/** Stable empty set used as the "no expanded folders" value in flat view mode. */
const EMPTY_EXPANDED_SET: Set<string> = new Set<string>();

/** Count all file nodes in a tree recursively. */
const countTreeFiles = (nodes: Array<TreeNode>): number => {
  let count = 0;
  for (const node of nodes) {
    if (node.type === "file") count++;
    else count += countTreeFiles(node.children);
  }
  return count;
};

type ChangesTreeViewProps = {
  workspaceId: string;
  viewMode: ViewMode;
  scope?: DiffScope;
  searchMatchingPaths?: Set<string> | null;
  onDiscardFile?: (filePath: string) => void;
  /**
   * When set, a file click calls this instead of opening a global diff tab. The
   * ChangesPanel passes its own selection setter so its embedded viewer is
   * driven by per-panel state rather than the shared diff-panel tab list.
   */
  onSelectFile?: (filePath: string, status: FileStatus) => void;
  /** The currently selected file path, highlighted in the list. */
  selectedPath?: string | null;
};

export const ChangesTreeView = ({
  workspaceId,
  viewMode,
  scope = "uncommitted",
  searchMatchingPaths,
  onDiscardFile,
  onSelectFile,
  selectedPath,
}: ChangesTreeViewProps): ReactElement => {
  const [fileBrowserState, setFileBrowserState] = useAtom(fileBrowserStateAtomFamily(workspaceId));
  const toggleFolder = useSetAtom(toggleChangesFolderAtom);
  const expandFolders = useSetAtom(expandChangesFoldersAtom);
  const openDiffTab = useSetAtom(openDiffTabAtom);

  const { agentID } = useWorkspacePageParams();
  const activeOperation = useActiveFileOperation(agentID);
  const workspace = useWorkspace(workspaceId);
  const { data: diff } = useWorkspaceDiff(workspaceId);
  const isDiffReady = workspace?.diffStatus === DiffStatus.READY && diff != null;

  const { tree, folderChangeCounts: allFolderChangeCounts } = useFileTree(workspaceId, scope);
  const perFileDiffMap = usePerFileDiffMap(workspaceId, scope);

  const isSearchActive = searchMatchingPaths != null;

  const changesTree = useMemo(() => buildChangesTree(tree), [tree]);

  const filteredChangesTree = useMemo(() => {
    if (!isSearchActive || !searchMatchingPaths) return changesTree;
    return filterTreeByPaths(changesTree, searchMatchingPaths);
  }, [changesTree, isSearchActive, searchMatchingPaths]);

  const compactedTree = useMemo(() => compactSingleChildFolders(filteredChangesTree), [filteredChangesTree]);

  const flatFiles = useMemo(() => {
    const all = getChangedFiles(tree);
    if (!isSearchActive || !searchMatchingPaths) return all;
    return all.filter((f) => searchMatchingPaths.has(f.path));
  }, [tree, isSearchActive, searchMatchingPaths]);

  const changesCount = useMemo(() => countTreeFiles(changesTree), [changesTree]);

  const visibleCount = useMemo(
    () => (isSearchActive ? countTreeFiles(filteredChangesTree) : changesCount),
    [isSearchActive, changesCount, filteredChangesTree],
  );

  const folderChangeCounts = useMemo(() => computeFolderChangeCounts(changesTree), [changesTree]);

  // Auto-expand all folders in the changes tree on first render and when tree changes
  const prevTreeIdRef = useRef<string>("");
  useEffect(() => {
    const allFolders = collectAllFolderPaths(compactedTree);
    const treeId = [...allFolders].sort().join(",");
    if (treeId !== prevTreeIdRef.current) {
      prevTreeIdRef.current = treeId;
      if (allFolders.length > 0) {
        expandFolders({ workspaceId, paths: allFolders });
      }
    }
  }, [compactedTree, expandFolders, workspaceId]);

  const expandedFoldersSet = useMemo(
    () => new Set(fileBrowserState.changesExpandedFolders),
    [fileBrowserState.changesExpandedFolders],
  );

  const flatRows = useMemo(
    () => flattenVisibleTreeWithDepth({ roots: compactedTree, expandedFolders: expandedFoldersSet }),
    [compactedTree, expandedFoldersSet],
  );

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const itemCount = viewMode === "tree" ? flatRows.length : flatFiles.length;

  const virtualizer = useVirtualizer({
    count: itemCount,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => FILE_TREE_ROW_HEIGHT,
    overscan: FILE_TREE_OVERSCAN,
    paddingStart: FILE_TREE_PADDING_TOP,
  });

  useAgentFileTracking({
    activeFilePath: activeOperation?.filePath,
    workspaceId,
    expandFolders,
  });

  const handleToggleExpand = useCallback(
    (path: string): void => {
      toggleFolder({ workspaceId, folderPath: path });
    },
    [toggleFolder, workspaceId],
  );

  const flatRowStatusMap = useMemo(
    () => new Map<string, FileStatus>(flatRows.map((r) => [r.node.path, r.node.status ?? "M"])),
    [flatRows],
  );
  const flatFileStatusMap = useMemo(
    () => new Map<string, FileStatus>(flatFiles.map((f) => [f.path, f.status ?? "M"])),
    [flatFiles],
  );

  const handleFileClick = useCallback(
    (path: string): void => {
      const statusMap = viewMode === "tree" ? flatRowStatusMap : flatFileStatusMap;
      const status = statusMap.get(path);
      if (status == null) {
        return;
      }

      if (onSelectFile) {
        onSelectFile(path, status);
        return;
      }
      openDiffTab({ workspaceId, filePath: path, status, scope });
    },
    [viewMode, flatRowStatusMap, flatFileStatusMap, onSelectFile, openDiffTab, workspaceId, scope],
  );

  const setExpandedFolders = useCallback(
    (update: (prev: Array<string>) => Array<string>): void => {
      setFileBrowserState((prev) => ({ ...prev, changesExpandedFolders: update(prev.changesExpandedFolders) }));
    },
    [setFileBrowserState],
  );

  const handleCollapseChildren = useCollapseChildren({
    flatRows,
    expandedFolders: fileBrowserState.changesExpandedFolders,
    setExpandedFolders,
  });

  const treeNodeMap = useTreeNodeMap(compactedTree);

  // Keyboard navigation items differ by view mode
  const keyboardItems = useMemo(() => {
    if (viewMode === "tree") {
      return flatRows.map((r) => r.node);
    }
    return flatFiles.map((f) => ({ path: f.path, type: "file" as const }));
  }, [viewMode, flatRows, flatFiles]);

  const { focusedIndex, setFocusedIndex, onKeyDown } = useKeyboardNavigation({
    items: keyboardItems,
    expandedFolders: viewMode === "tree" ? expandedFoldersSet : EMPTY_EXPANDED_SET,
    onToggleExpand: handleToggleExpand,
    onFileOpen: handleFileClick,
  });

  useEffect(() => {
    if (focusedIndex >= 0) {
      virtualizer.scrollToIndex(focusedIndex, { align: "auto" });
    }
  }, [focusedIndex, virtualizer]);

  const getNodeData = useCallback(
    (node: TreeNode): { isExpanded: boolean; folderChangeCount: number } => ({
      isExpanded: expandedFoldersSet.has(node.path),
      folderChangeCount: allFolderChangeCounts.get(node.path) ?? folderChangeCounts.get(node.path) ?? 0,
    }),
    [expandedFoldersSet, allFolderChangeCounts, folderChangeCounts],
  );

  if (isSearchActive && visibleCount === 0) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        <Text size="2" color="gray">
          No matches
        </Text>
      </Flex>
    );
  }

  if (changesCount === 0) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        {isDiffReady ? (
          <Text size="2" color="gray">
            No changes
          </Text>
        ) : (
          <Spinner size="2" />
        )}
      </Flex>
    );
  }

  return (
    <div
      ref={scrollContainerRef}
      className={styles.scrollContainer}
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="tree"
      data-testid={ElementIds.FILE_BROWSER_CHANGES_TREE}
    >
      <div style={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
        {virtualizer.getVirtualItems().map((virtualItem) => {
          if (viewMode === "flat") {
            const entry = flatFiles[virtualItem.index];
            const fileDiff = perFileDiffMap.get(entry.path);

            return (
              <div
                key={entry.path}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: FILE_TREE_ROW_HEIGHT,
                  transform: `translateY(${virtualItem.start}px)`,
                }}
                onClick={() => setFocusedIndex(virtualItem.index)}
              >
                <FileContextMenu
                  context={{
                    filePath: entry.path,
                    isFolder: false,
                    fileStatus: entry.status,
                    isBinary: isBinaryFile(entry.name),
                    source: "flat-list",
                  }}
                  workspaceId={workspaceId}
                >
                  <FlatListRow
                    entry={entry}
                    isFocused={virtualItem.index === focusedIndex}
                    isSelected={entry.path === selectedPath}
                    addedLines={fileDiff?.addedLines}
                    removedLines={fileDiff?.removedLines}
                    onFileClick={handleFileClick}
                    onDiscardFile={onDiscardFile}
                  />
                </FileContextMenu>
              </div>
            );
          }

          // Tree mode
          const { node, depth } = flatRows[virtualItem.index];
          const { isExpanded, folderChangeCount } = getNodeData(node);
          const treeNode = treeNodeMap.get(node.path);
          const descendantFolderPaths =
            treeNode && treeNode.type === "directory" ? collectDescendantFolderPaths(treeNode) : undefined;

          const fileDiff = node.type === "file" ? perFileDiffMap.get(node.path) : undefined;

          return (
            <div
              key={node.path}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: FILE_TREE_ROW_HEIGHT,
                transform: `translateY(${virtualItem.start}px)`,
              }}
              onClick={() => setFocusedIndex(virtualItem.index)}
            >
              <FileContextMenu
                context={{
                  filePath: node.path,
                  isFolder: node.type === "directory",
                  fileStatus: node.status,
                  isBinary: isBinaryFile(node.name),
                  source: "tree",
                }}
                workspaceId={workspaceId}
                allDescendantFolderPaths={descendantFolderPaths}
                isExpanded={isExpanded}
                onCollapseChildren={handleCollapseChildren}
              >
                <TreeRow
                  node={node}
                  depth={depth}
                  isExpanded={isExpanded}
                  isFocused={virtualItem.index === focusedIndex}
                  isActiveFile={node.path === activeOperation?.filePath}
                  isSelected={node.path === selectedPath}
                  folderChangeCount={folderChangeCount}
                  addedLines={fileDiff?.addedLines}
                  removedLines={fileDiff?.removedLines}
                  onToggleExpand={handleToggleExpand}
                  onFileClick={handleFileClick}
                  onDiscardFile={onDiscardFile}
                />
              </FileContextMenu>
            </div>
          );
        })}
      </div>
    </div>
  );
};
