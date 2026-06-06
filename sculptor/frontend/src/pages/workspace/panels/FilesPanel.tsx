import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { diffStateKey, FILES_DIFF_SCOPE } from "~/pages/workspace/components/diffPanel/atoms.ts";

import { fileBrowserStateAtomFamily } from "./fileBrowser/atoms.ts";
import { EmptyState, SkeletonLoading } from "./fileBrowser/EmptyStates.tsx";
import { FileTree } from "./fileBrowser/FileTree.tsx";
import { useFileTree } from "./fileBrowser/hooks.ts";
import { MasterDetailPanel } from "./MasterDetailPanel.tsx";

/**
 * "Files" panel — the file tree (REQ-PANEL-1). Selecting a file opens it in this
 * panel's own master-detail viewer (REQ-DIFF-1). The secondary header icons
 * (flat-list toggle, collapse-all, search, refresh) are intentionally dropped
 * this iteration (REQ-ICONS-1); see removed-icons.md.
 */
export const FilesPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));
  const { tree, isPending } = useFileTree(workspaceID ?? "", "vs-target-branch");

  if (!workspaceID) return null;

  const hasFiles = tree.length > 0;
  const stateKey = diffStateKey(workspaceID, FILES_DIFF_SCOPE);

  return (
    <MasterDetailPanel workspaceId={workspaceID} stateKey={stateKey}>
      <Flex direction="column" height="100%" overflow="hidden" data-testid={ElementIds.FILE_BROWSER_PANEL}>
        {isPending && !hasFiles ? (
          <SkeletonLoading />
        ) : !hasFiles ? (
          <EmptyState />
        ) : (
          <FileTree
            workspaceId={workspaceID}
            viewMode={fileBrowserState.viewMode}
            searchMatchingPaths={null}
            diffStateKey={stateKey}
          />
        )}
      </Flex>
    </MasterDetailPanel>
  );
};
