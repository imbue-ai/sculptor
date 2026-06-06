import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { fileBrowserStateAtomFamily } from "./fileBrowser/atoms.ts";
import { ChangesTabContent } from "./fileBrowser/ChangesTabContent.tsx";
import { MasterDetailPanel } from "./MasterDetailPanel.tsx";

/**
 * "Changes" panel (REQ-PANEL-1). Selecting a changed file opens its diff in this
 * panel's master-detail viewer (REQ-DIFF-1). Changes uses the default diff scope
 * (the workspaceId), so files opened from chat / @-mentions land here too.
 */
export const ChangesPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));

  if (!workspaceID) return null;

  return (
    <MasterDetailPanel workspaceId={workspaceID} stateKey={workspaceID}>
      <Flex direction="column" height="100%" overflow="hidden">
        <ChangesTabContent workspaceId={workspaceID} viewMode={fileBrowserState.viewMode} />
      </Flex>
    </MasterDetailPanel>
  );
};
