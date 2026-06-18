import { useCallback, useEffect, useMemo, useRef } from "react";

import type { TreeNode } from "./types.ts";
import type { FlatRowEntry } from "./utils.ts";
import { collectAllFolderPaths, collectDescendantFolderPaths, getAncestorPaths } from "./utils.ts";

type UseAgentFileTrackingParams = {
  activeFilePath: string | undefined;
  workspaceId: string;
  expandFolders: (params: { workspaceId: string; paths: Array<string> }) => void;
};

/**
 * Auto-expand ancestor folders when the agent actively operates on a file
 * (e.g. writes, creates, deletes).
 */
export const useAgentFileTracking = ({
  activeFilePath,
  workspaceId,
  expandFolders,
}: UseAgentFileTrackingParams): void => {
  const prevActivePathRef = useRef<string | null>(null);
  useEffect(() => {
    const activePath = activeFilePath ?? null;
    if (activePath && activePath !== prevActivePathRef.current) {
      const ancestors = getAncestorPaths(activePath);
      if (ancestors.length > 0) {
        expandFolders({ workspaceId, paths: ancestors });
      }
    }
    prevActivePathRef.current = activePath;
  }, [activeFilePath, expandFolders, workspaceId]);
};

type UseSearchAutoExpandParams = {
  isSearchActive: boolean;
  tree: Array<TreeNode>;
  currentExpandedFolders: Array<string>;
  expandFolders: (params: { workspaceId: string; paths: Array<string> }) => void;
  setExpandedFolders: (update: (prev: Array<string>) => Array<string>) => void;
  workspaceId: string;
};

/**
 * When a search becomes active, auto-expand all folders in the filtered tree.
 * When the search is cleared, restore the previously saved expand state.
 *
 * Folders are only auto-expanded once when search first activates.
 * Subsequent tree changes (e.g. typing more characters) do not force
 * folders back open, so the user can collapse folders during search.
 */
export const useSearchAutoExpand = ({
  isSearchActive,
  tree,
  currentExpandedFolders,
  expandFolders,
  setExpandedFolders,
  workspaceId,
}: UseSearchAutoExpandParams): void => {
  // We intentionally omit currentExpandedFolders from deps so that
  // user-driven collapse/expand during search doesn't trigger re-expansion.
  const preSearchExpandedRef = useRef<Array<string> | null>(null);
  const expandedFoldersRef = useRef(currentExpandedFolders);
  expandedFoldersRef.current = currentExpandedFolders;
  const wasSearchActiveRef = useRef(false);

  useEffect(() => {
    if (isSearchActive) {
      // Save pre-search state on first activation
      if (preSearchExpandedRef.current === null) {
        preSearchExpandedRef.current = expandedFoldersRef.current;
      }

      // Only auto-expand when search first activates, not on subsequent tree changes
      if (!wasSearchActiveRef.current) {
        const allFolders = collectAllFolderPaths(tree);
        if (allFolders.length > 0) {
          expandFolders({ workspaceId, paths: allFolders });
        }
      }
    } else if (preSearchExpandedRef.current !== null) {
      const savedFolders = preSearchExpandedRef.current;
      preSearchExpandedRef.current = null;
      setExpandedFolders(() => savedFolders);
    }
    wasSearchActiveRef.current = isSearchActive;
  }, [isSearchActive, tree, expandFolders, workspaceId, setExpandedFolders]);
};

/**
 * Build a lookup map from file path to TreeNode, useful for quickly
 * retrieving descendant folder paths in context menus.
 */
export const useTreeNodeMap = (tree: Array<TreeNode>): Map<string, TreeNode> => {
  return useMemo(() => {
    const map = new Map<string, TreeNode>();
    const walk = (nodes: Array<TreeNode>): void => {
      for (const node of nodes) {
        map.set(node.path, node);
        if (node.children.length > 0) walk(node.children);
      }
    };
    walk(tree);
    return map;
  }, [tree]);
};

/**
 * Returns a callback that collapses a folder and all its descendant folders.
 */
export const useCollapseChildren = ({
  flatRows,
  expandedFolders,
  setExpandedFolders,
}: {
  flatRows: Array<FlatRowEntry>;
  expandedFolders: Array<string>;
  setExpandedFolders: (update: (prev: Array<string>) => Array<string>) => void;
}): ((folderPath: string) => void) => {
  return useCallback(
    (folderPath: string): void => {
      const row = flatRows.find((r) => r.node.path === folderPath);
      if (!row) return;
      const descendantPaths = collectDescendantFolderPaths(row.node);
      const newExpanded = expandedFolders.filter((p) => p !== folderPath && !descendantPaths.includes(p));
      setExpandedFolders(() => newExpanded);
    },
    [flatRows, expandedFolders, setExpandedFolders],
  );
};
