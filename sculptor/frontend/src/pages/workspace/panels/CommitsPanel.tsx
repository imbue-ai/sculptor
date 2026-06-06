import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { COMMITS_DIFF_SCOPE, diffStateKey } from "~/pages/workspace/components/diffPanel/atoms.ts";

import { HistoryTabContent } from "./historyPanel/HistoryTabContent.tsx";
import { MasterDetailPanel } from "./MasterDetailPanel.tsx";

/**
 * "Commits" panel — commit history (REQ-PANEL-1). Selecting a file within a
 * commit opens its diff in this panel's master-detail viewer (REQ-DIFF-1).
 */
export const CommitsPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();

  if (!workspaceID) return null;

  const stateKey = diffStateKey(workspaceID, COMMITS_DIFF_SCOPE);

  return (
    <MasterDetailPanel workspaceId={workspaceID} stateKey={stateKey}>
      <Flex direction="column" height="100%" overflow="hidden">
        <HistoryTabContent workspaceId={workspaceID} viewMode="flat" diffStateKey={stateKey} />
      </Flex>
    </MasterDetailPanel>
  );
};
