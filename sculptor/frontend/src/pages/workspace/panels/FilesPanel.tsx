import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { fileBrowserStateAtomFamily } from "./fileBrowser/atoms.ts";
import { EmptyState, SkeletonLoading } from "./fileBrowser/EmptyStates.tsx";
import { FileTree } from "./fileBrowser/FileTree.tsx";
import { useFileTree } from "./fileBrowser/hooks.ts";

/**
 * "Files" panel — the file tree, split out of the old three-tab FileBrowserPanel
 * into its own registered panel (REQ-PANEL-1). The secondary header icons
 * (flat-list toggle, collapse-all, search, refresh) are intentionally dropped
 * this iteration (REQ-ICONS-1); see removed-icons.md.
 */
export const FilesPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));
  const { tree, isPending } = useFileTree(workspaceID ?? "", "vs-target-branch");

  if (!workspaceID) return null;

  const hasFiles = tree.length > 0;

  return (
    <Flex direction="column" height="100%" overflow="hidden" data-testid={ElementIds.FILE_BROWSER_PANEL}>
      {isPending && !hasFiles ? (
        <SkeletonLoading />
      ) : !hasFiles ? (
        <EmptyState />
      ) : (
        <FileTree workspaceId={workspaceID} viewMode={fileBrowserState.viewMode} searchMatchingPaths={null} />
      )}
    </Flex>
  );
};
