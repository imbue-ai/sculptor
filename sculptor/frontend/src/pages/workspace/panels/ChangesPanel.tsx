import { Flex } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { collapseAllChangesFoldersAtom, fileBrowserStateAtomFamily, toggleViewModeAtom } from "./fileBrowser/atoms.ts";
import { ChangesTabContent } from "./fileBrowser/ChangesTabContent.tsx";
import { useFileSearch } from "./fileBrowser/hooks.ts";
import { MasterDetailPanel } from "./MasterDetailPanel.tsx";
import type { MasterDetailHeaderConfig } from "./MasterDetailTreeHeader.tsx";

/**
 * "Changes" panel (REQ-PANEL-1). Selecting a changed file opens its diff in this
 * panel's master-detail viewer (REQ-DIFF-1). Changes uses the default diff scope
 * (the workspaceId), so files opened from chat / @-mentions land here too. The
 * tree header's search filters the changed-files tree.
 */
export const ChangesPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));
  const { searchQuery, viewMode } = fileBrowserState;
  const { matchingPaths } = useFileSearch(workspaceID ?? "", searchQuery);
  const searchMatchingPaths = searchQuery.trim() !== "" ? matchingPaths : null;

  const toggleViewMode = useSetAtom(toggleViewModeAtom);
  const collapseAllChangesFolders = useSetAtom(collapseAllChangesFoldersAtom);
  const handleToggleViewMode = useCallback((): void => {
    if (workspaceID) toggleViewMode({ workspaceId: workspaceID });
  }, [workspaceID, toggleViewMode]);
  const handleCollapseAll = useCallback((): void => {
    if (workspaceID) collapseAllChangesFolders({ workspaceId: workspaceID });
  }, [workspaceID, collapseAllChangesFolders]);

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

  return (
    <MasterDetailPanel workspaceId={workspaceID} stateKey={workspaceID} scope="changes" header={header}>
      <Flex direction="column" flexGrow="1" minHeight="0" overflow="hidden">
        <ChangesTabContent workspaceId={workspaceID} viewMode={viewMode} searchMatchingPaths={searchMatchingPaths} />
      </Flex>
    </MasterDetailPanel>
  );
};
