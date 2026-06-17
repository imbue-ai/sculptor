import { Flex } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { diffStateKey, FILES_DIFF_SCOPE } from "~/pages/workspace/components/diffPanel/atoms.ts";

import { collapseAllFoldersAtom, fileBrowserStateAtomFamily, toggleViewModeAtom } from "./fileBrowser/atoms.ts";
import { EmptyState, SkeletonLoading } from "./fileBrowser/EmptyStates.tsx";
import { FileTree } from "./fileBrowser/FileTree.tsx";
import { useFileSearch, useFileTree } from "./fileBrowser/hooks.ts";
import { MasterDetailPanel } from "./MasterDetailPanel.tsx";
import type { MasterDetailHeaderConfig } from "./MasterDetailTreeHeader.tsx";

/**
 * "Files" panel — the file tree (REQ-PANEL-1). Selecting a file opens it in this
 * panel's own master-detail viewer (REQ-DIFF-1). The tree header carries the
 * search box, the view-options "…" menu, and the hide-tree toggle.
 */
export const FilesPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));
  const { tree, isPending } = useFileTree(workspaceID ?? "", "vs-target-branch");

  const { searchQuery, viewMode } = fileBrowserState;
  const { matchingPaths } = useFileSearch(workspaceID ?? "", searchQuery);
  const searchMatchingPaths = searchQuery.trim() !== "" ? matchingPaths : null;

  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const collapseAllFolders = useSetAtom(collapseAllFoldersAtom);
  const handleToggleViewMode = useCallback((): void => {
    if (workspaceID) toggleViewMode({ workspaceId: workspaceID });
  }, [workspaceID, toggleViewMode]);
  const handleCollapseAll = useCallback((): void => {
    if (workspaceID) collapseAllFolders({ workspaceId: workspaceID });
  }, [workspaceID, collapseAllFolders]);

  const header: MasterDetailHeaderConfig = useMemo(
    () => ({
      hasSearch: true,
      viewMode,
      onToggleViewMode: handleToggleViewMode,
      onCollapseAll: handleCollapseAll,
      collapseLabel: "Collapse folders",
    }),
    [viewMode, handleToggleViewMode, handleCollapseAll],
  );

  if (!workspaceID) return null;

  const hasFiles = tree.length > 0;
  const stateKey = diffStateKey(workspaceID, FILES_DIFF_SCOPE);

  return (
    <MasterDetailPanel workspaceId={workspaceID} stateKey={stateKey} scope={FILES_DIFF_SCOPE} header={header}>
      <Flex direction="column" flexGrow="1" minHeight="0" overflow="hidden" data-testid={ElementIds.FILE_BROWSER_PANEL}>
        {isPending && !hasFiles ? (
          <SkeletonLoading />
        ) : !hasFiles ? (
          <EmptyState />
        ) : (
          <FileTree
            workspaceId={workspaceID}
            viewMode={viewMode}
            searchMatchingPaths={searchMatchingPaths}
            diffStateKey={stateKey}
          />
        )}
      </Flex>
    </MasterDetailPanel>
  );
};
