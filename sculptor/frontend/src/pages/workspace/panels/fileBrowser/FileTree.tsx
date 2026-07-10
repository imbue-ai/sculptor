import { Flex, Text } from "@radix-ui/themes";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { type ReactElement, useCallback, useEffect, useId, useMemo, useRef } from "react";

import { ElementIds } from "~/api";
import { VerticalOverlayScrollbar } from "~/components/VerticalOverlayScrollbar.tsx";

import { activeAgentIdAtomFamily } from "../workspaceAgentActions.ts";
import { expandFoldersAtom, fileBrowserStateAtomFamily, toggleFolderAtom } from "./atoms.ts";
import { FileContextMenu } from "./FileContextMenu.tsx";
import styles from "./FileTree.module.scss";
import { FlatListRow } from "./FlatListRow.tsx";
import { useFileTree } from "./hooks.ts";
import { TreeRow } from "./TreeRow.tsx";
import type { TreeNode, ViewMode } from "./types.ts";
import { useActiveFileOperation } from "./useActiveFileOperation.ts";
import { useFocusFolderHighlight } from "./useFocusFolderHighlight.ts";
import { useKeyboardNavigation } from "./useKeyboardNavigation.ts";
import { useAgentFileTracking, useCollapseChildren, useSearchAutoExpand, useTreeNodeMap } from "./useTreeView.ts";
import {
  collectDescendantFolderPaths,
  compactSingleChildFolders,
  FILE_TREE_OVERSCAN,
  FILE_TREE_PADDING_TOP,
  FILE_TREE_ROW_HEIGHT,
  filterTreeByPaths,
  flattenVisibleTreeWithDepth,
  getAllFiles,
  isBinaryFile,
} from "./utils.ts";

const SCROLL_SAVE_DEBOUNCE_MS = 200;

type FileTreeProps = {
  workspaceId: string;
  viewMode: ViewMode;
  searchMatchingPaths?: Set<string> | null;
  /**
   * A file click calls this with the clicked path. The FilesPanel drives its
   * embedded viewer from per-panel selection state rather than the shared
   * diff-panel tab list.
   */
  onSelectFile: (path: string) => void;
  /** The currently selected file path, highlighted in the list. */
  selectedPath?: string | null;
};

export const FileTree = ({
  workspaceId,
  viewMode,
  searchMatchingPaths,
  onSelectFile,
  selectedPath,
}: FileTreeProps): ReactElement => {
  const [fileBrowserState, setFileBrowserState] = useAtom(fileBrowserStateAtomFamily(workspaceId));
  const toggleFolder = useSetAtom(toggleFolderAtom);
  const expandFolders = useSetAtom(expandFoldersAtom);

  // Track file operations of the workspace's current agent, resolved from the
  // section shell rather than the route: activating a different center tab
  // doesn't navigate, so the route's agent id goes stale.
  const agentId = useAtomValue(activeAgentIdAtomFamily(workspaceId));
  const activeOperation = useActiveFileOperation(agentId);

  const { tree: rawTree, folderChangeCounts } = useFileTree(workspaceId, "vs-target-branch");

  const isSearchActive = searchMatchingPaths != null;

  const filteredTree = useMemo(() => {
    if (!isSearchActive || !searchMatchingPaths) return rawTree;
    return filterTreeByPaths(rawTree, searchMatchingPaths);
  }, [rawTree, isSearchActive, searchMatchingPaths]);

  const tree = useMemo(() => compactSingleChildFolders(filteredTree), [filteredTree]);

  const flatFiles = useMemo(() => {
    const all = getAllFiles(rawTree);
    if (!isSearchActive || !searchMatchingPaths) return all;
    return all.filter((f) => searchMatchingPaths.has(f.path));
  }, [rawTree, isSearchActive, searchMatchingPaths]);

  const expandedFoldersSet = useMemo(
    () => new Set(fileBrowserState.expandedFolders),
    [fileBrowserState.expandedFolders],
  );

  // Save expand state before search and auto-expand all filtered folders.
  useSearchAutoExpand({
    isSearchActive,
    tree,
    currentExpandedFolders: fileBrowserState.expandedFolders,
    expandFolders,
    setExpandedFolders: (update) => {
      setFileBrowserState((prev) => ({ ...prev, expandedFolders: update(prev.expandedFolders) }));
    },
    workspaceId,
  });

  const flatRows = useMemo(
    () => flattenVisibleTreeWithDepth({ roots: tree, expandedFolders: expandedFoldersSet }),
    [tree, expandedFoldersSet],
  );

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  // Links the scroll container to the overlay scrollbar's `aria-controls`.
  const scrollContainerId = useId();

  const itemCount = viewMode === "tree" ? flatRows.length : flatFiles.length;

  const virtualizer = useVirtualizer({
    count: itemCount,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => FILE_TREE_ROW_HEIGHT,
    overscan: FILE_TREE_OVERSCAN,
    paddingStart: FILE_TREE_PADDING_TOP,
  });

  // Restore scroll position on mount
  useEffect(() => {
    if (scrollContainerRef.current && fileBrowserState.scrollPosition > 0) {
      scrollContainerRef.current.scrollTop = fileBrowserState.scrollPosition;
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Save scroll position (debounced)
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return (): void => {
      if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    };
  }, []);
  const handleScroll = useCallback((): void => {
    if (scrollTimerRef.current) {
      clearTimeout(scrollTimerRef.current);
    }
    scrollTimerRef.current = setTimeout(() => {
      const scrollTop = scrollContainerRef.current?.scrollTop ?? 0;
      setFileBrowserState((prev) => ({ ...prev, scrollPosition: scrollTop }));
    }, SCROLL_SAVE_DEBOUNCE_MS);
  }, [setFileBrowserState]);

  // Auto-expand ancestor folders when agent operates on a file
  useAgentFileTracking({
    activeFilePath: activeOperation?.filePath,
    workspaceId,
    expandFolders,
  });

  // Auto-scroll to the active file when it changes
  useEffect(() => {
    if (!activeOperation?.filePath) return;
    const index = flatRows.findIndex((r) => r.node.path === activeOperation.filePath);
    if (index >= 0) {
      virtualizer.scrollToIndex(index, { align: "auto" });
    }
  }, [activeOperation?.filePath, flatRows, virtualizer]);

  useFocusFolderHighlight({
    workspaceId,
    flatRows,
    virtualizer,
    scrollContainerRef,
  });

  const handleToggleExpand = useCallback(
    (path: string): void => {
      toggleFolder({ workspaceId, folderPath: path });
    },
    [toggleFolder, workspaceId],
  );

  const handleFileClick = useCallback(
    (path: string): void => {
      onSelectFile(path);
    },
    [onSelectFile],
  );

  const handleCollapseChildren = useCollapseChildren({
    flatRows,
    expandedFolders: fileBrowserState.expandedFolders,
    setExpandedFolders: (update) => {
      setFileBrowserState((prev) => ({ ...prev, expandedFolders: update(prev.expandedFolders) }));
    },
  });

  const treeNodeMap = useTreeNodeMap(tree);

  const keyboardItems = useMemo(() => {
    if (viewMode === "tree") {
      return flatRows.map((r) => r.node);
    }
    return flatFiles.map((f) => ({ path: f.path, type: "file" as const }));
  }, [viewMode, flatRows, flatFiles]);

  const emptyExpandedSet = useMemo(() => new Set<string>(), []);

  const { focusedIndex, setFocusedIndex, onKeyDown } = useKeyboardNavigation({
    items: keyboardItems,
    expandedFolders: viewMode === "tree" ? expandedFoldersSet : emptyExpandedSet,
    onToggleExpand: handleToggleExpand,
    onFileOpen: handleFileClick,
  });

  // Scroll focused row into view
  useEffect(() => {
    if (focusedIndex >= 0) {
      virtualizer.scrollToIndex(focusedIndex, { align: "auto" });
    }
  }, [focusedIndex, virtualizer]);

  const getNodeData = useCallback(
    (node: TreeNode, depth: number): { depth: number; isExpanded: boolean; folderChangeCount: number } => ({
      depth,
      isExpanded: expandedFoldersSet.has(node.path),
      folderChangeCount: folderChangeCounts.get(node.path) ?? 0,
    }),
    [expandedFoldersSet, folderChangeCounts],
  );

  if (isSearchActive && itemCount === 0) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        <Text size="2" color="gray">
          No matches
        </Text>
      </Flex>
    );
  }

  return (
    <div
      ref={scrollContainerRef}
      id={scrollContainerId}
      className={styles.scrollContainer}
      onScroll={handleScroll}
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="tree"
      data-testid={ElementIds.FILE_BROWSER_FILE_TREE}
    >
      <div style={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
        {virtualizer.getVirtualItems().map((virtualItem) => {
          if (viewMode === "flat") {
            const entry = flatFiles[virtualItem.index];

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
                    onFileClick={handleFileClick}
                  />
                </FileContextMenu>
              </div>
            );
          }

          // Tree mode
          const { node, depth } = flatRows[virtualItem.index];
          const { isExpanded, folderChangeCount } = getNodeData(node, depth);
          const treeNode = treeNodeMap.get(node.path);
          const descendantFolderPaths =
            treeNode && treeNode.type === "directory" ? collectDescendantFolderPaths(treeNode) : undefined;

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
                  onToggleExpand={handleToggleExpand}
                  onFileClick={handleFileClick}
                />
              </FileContextMenu>
            </div>
          );
        })}
      </div>
      <VerticalOverlayScrollbar
        scrollRef={scrollContainerRef}
        scrollContainerId={scrollContainerId}
        thumbTestId={ElementIds.FILE_BROWSER_SCROLLBAR_THUMB}
      />
    </div>
  );
};
