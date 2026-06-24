// The Files panel: a single-instance left-section panel that pairs the workspace
// file tree (the list) with an embedded DiffViewer (the detail). It owns its own
// selection — a file-view of the clicked file — and feeds it to its own viewer
// instance, so there is no shared "active diff" singleton (FCC-01/02/03). The
// proven file-tree behavior (flat + tree variants, path/tilde display, symlink
// handling, search) is migrated, not redesigned.

import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { ElementIds } from "~/api";
import { registerPanelComponent } from "~/components/sections/registry/panelRegistry.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import type { DiffSelection, TreeViewOptions } from "~/pages/workspace/components/diffViewer/index.ts";
import { DiffViewer } from "~/pages/workspace/components/diffViewer/index.ts";

import { ExplorerLayout } from "./ExplorerLayout.tsx";
import { ExplorerTreeHeader } from "./ExplorerTreeHeader.tsx";
import { collapseAllFoldersAtom, fileBrowserStateAtomFamily, toggleViewModeAtom } from "./fileBrowser/atoms.ts";
import { EmptyState, SkeletonLoading } from "./fileBrowser/EmptyStates.tsx";
import { FileTree } from "./fileBrowser/FileTree.tsx";
import { useFileSearch, useFileTree } from "./fileBrowser/hooks.ts";
import styles from "./FilesPanel.module.scss";

/** Renders the file tree list, an empty/loading placeholder, or the tree. */
const FilesPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceId));
  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const collapseAllFolders = useSetAtom(collapseAllFoldersAtom);

  // Per-panel selection: the file currently shown in this panel's viewer.
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");

  const { tree, isPending } = useFileTree(workspaceId, "vs-target-branch");
  const { matchingPaths } = useFileSearch(workspaceId, searchQuery);

  const { viewMode } = fileBrowserState;

  const searchMatchingPaths = useMemo(() => {
    if (searchQuery.length === 0) return null;
    return matchingPaths;
  }, [searchQuery, matchingPaths]);

  const handleSelectFile = useCallback((path: string): void => {
    setSelectedPath(path);
  }, []);

  const handleToggleViewMode = useCallback((): void => {
    toggleViewMode({ workspaceId });
  }, [toggleViewMode, workspaceId]);

  const handleCollapseAll = useCallback((): void => {
    collapseAllFolders({ workspaceId });
  }, [collapseAllFolders, workspaceId]);

  const selection = useMemo((): DiffSelection | null => {
    if (selectedPath === null) return null;
    return { kind: "file-view", filePath: selectedPath };
  }, [selectedPath]);

  // The flat/tree + collapse-all controls live in the viewer's triple-dot menu (FCC-07).
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
      hasSelection={selection !== null}
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
  // Key on the workspace id so switching workspaces resets the panel's local
  // selection state instead of carrying a stale file path across workspaces.
  return <FilesPanelContent key={workspaceId} workspaceId={workspaceId} />;
};

registerPanelComponent("files", FilesPanel);
