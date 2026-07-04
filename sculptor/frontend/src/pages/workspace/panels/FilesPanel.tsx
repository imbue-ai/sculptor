// The Files panel: a single-instance left-section panel that pairs the workspace
// file tree (the list) with an embedded DiffViewer (the detail). It owns its own
// selection — a file-view of the clicked file — and feeds it to its own viewer
// instance, so there is no shared "active diff" singleton. The file tree supports
// flat + tree variants, path/tilde display, symlink handling, and search.

import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import { activeDiffTabAtomFamily, fileViewSelectionFromTab } from "~/pages/workspace/components/diffPanel/atoms.ts";
import type { DiffSelection, TreeViewOptions } from "~/pages/workspace/components/diffViewer/index.ts";
import { DiffViewer } from "~/pages/workspace/components/diffViewer/index.ts";

import { ExplorerLayout } from "./ExplorerLayout.tsx";
import { ExplorerTreeHeader } from "./ExplorerTreeHeader.tsx";
import {
  collapseAllFoldersAtom,
  fileBrowserViewModeAtomFamily,
  filesPanelSelectionAtomFamily,
  toggleViewModeAtom,
} from "./fileBrowser/atoms.ts";
import { EmptyState, SkeletonLoading } from "./fileBrowser/EmptyStates.tsx";
import { FileTree } from "./fileBrowser/FileTree.tsx";
import { useFileSearch, useFileTree } from "./fileBrowser/hooks.ts";
import styles from "./FilesPanel.module.scss";
import { reconcileSelectionByRecency } from "./selectionRecency.ts";

/** Renders the file tree list, an empty/loading placeholder, or the tree. */
const FilesPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const viewMode = useAtomValue(fileBrowserViewModeAtomFamily(workspaceId));
  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const collapseAllFolders = useSetAtom(collapseAllFoldersAtom);

  // Per-panel selection from a local tree click, stamped so it can be reconciled with
  // the atom-driven selection (an agent open) by recency. Persisted per-workspace in
  // an atom — not React state — so the open file survives the panel remounting on a
  // section-tab switch or a section maximize/restore.
  const [localSelection, setLocalSelection] = useAtom(filesPanelSelectionAtomFamily(workspaceId));

  // The shared active diff tab — written when an agent opens a file (sculpt open-file,
  // a chat file-chip, plan mode). Reading it here makes those opens render in this
  // panel's single embedded viewer, not just reveal the panel.
  const activeTab = useAtomValue(activeDiffTabAtomFamily(workspaceId));

  const [searchQuery, setSearchQuery] = useState("");

  const { tree, isPending } = useFileTree(workspaceId, "vs-target-branch");
  const { matchingPaths } = useFileSearch(workspaceId, searchQuery);

  const searchMatchingPaths = useMemo(() => {
    if (searchQuery.length === 0) return null;
    return matchingPaths;
  }, [searchQuery, matchingPaths]);

  const handleSelectFile = useCallback(
    (path: string): void => {
      setLocalSelection({ filePath: path, at: Date.now() });
    },
    [setLocalSelection],
  );

  const handleToggleViewMode = useCallback((): void => {
    toggleViewMode({ workspaceId });
  }, [toggleViewMode, workspaceId]);

  const handleCollapseAll = useCallback((): void => {
    collapseAllFolders({ workspaceId });
  }, [collapseAllFolders, workspaceId]);

  // Reconcile the local click selection with the atom-driven one (an agent open) by
  // recency: whichever was activated last wins, so a local click still takes effect
  // after an agent open and vice-versa.
  const selection = useMemo(
    (): DiffSelection | null =>
      reconcileSelectionByRecency({
        local: localSelection,
        tab: activeTab,
        tabKind: "file-view",
        toSelection: (local) => ({ kind: "file-view", filePath: local.filePath }),
        fromTab: fileViewSelectionFromTab,
      }),
    [localSelection, activeTab],
  );

  // The path highlighted in the tree mirrors whatever the viewer is showing.
  const selectedPath = selection?.kind === "file-view" ? selection.filePath : null;

  // The flat/tree + collapse-all controls live in the viewer's triple-dot menu.
  const treeOptions: TreeViewOptions = {
    viewMode,
    onToggleViewMode: handleToggleViewMode,
    onCollapseAll: handleCollapseAll,
    collapseLabel: "Collapse folders",
  };

  const hasFiles = tree.length > 0;

  const list = (
    <div className={styles.list} data-testid={ElementIds.FILE_BROWSER_PANEL}>
      <ExplorerTreeHeader searchQuery={searchQuery} onSearchChange={setSearchQuery} placeholder="Search files…" />
      {isPending && !hasFiles ? (
        <SkeletonLoading />
      ) : !hasFiles ? (
        <EmptyState />
      ) : (
        <FileTree
          workspaceId={workspaceId}
          viewMode={viewMode}
          searchMatchingPaths={searchMatchingPaths}
          onSelectFile={handleSelectFile}
          selectedPath={selectedPath}
        />
      )}
    </div>
  );

  return (
    <ExplorerLayout
      list={list}
      detail={(sidebarToggle) => (
        <DiffViewer
          workspaceId={workspaceId}
          selection={selection}
          treeOptions={treeOptions}
          sidebarToggle={sidebarToggle}
        />
      )}
    />
  );
};

export const FilesPanel = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return null;
  }
  // Key on the workspace id so switching workspaces resets the panel's
  // transient state (e.g. the search query) instead of carrying it across
  // workspaces; the file selection is already per-workspace via its atom.
  return <FilesPanelContent key={workspaceId} workspaceId={workspaceId} />;
};
