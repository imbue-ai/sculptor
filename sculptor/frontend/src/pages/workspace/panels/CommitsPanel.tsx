import { Flex } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { COMMITS_DIFF_SCOPE, diffStateKey } from "~/pages/workspace/components/diffPanel/atoms.ts";

import { collapseAllCommitsAtom } from "./historyPanel/atoms.ts";
import { HistoryTabContent } from "./historyPanel/HistoryTabContent.tsx";
import { MasterDetailPanel } from "./MasterDetailPanel.tsx";
import type { MasterDetailHeaderConfig } from "./MasterDetailTreeHeader.tsx";

/**
 * "Commits" panel — commit history (REQ-PANEL-1). Selecting a file within a
 * commit opens its diff in this panel's master-detail viewer (REQ-DIFF-1).
 * Commits has no search, so its tree header is just the "…" (collapse) + the
 * hide toggle.
 */
export const CommitsPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const collapseAllCommits = useSetAtom(collapseAllCommitsAtom);
  const handleCollapseAll = useCallback((): void => {
    if (workspaceID) collapseAllCommits({ workspaceId: workspaceID });
  }, [workspaceID, collapseAllCommits]);

  const header: MasterDetailHeaderConfig = useMemo(
    () => ({ hasSearch: false, onCollapseAll: handleCollapseAll, collapseLabel: "Collapse commits" }),
    [handleCollapseAll],
  );

  if (!workspaceID) return null;

  const stateKey = diffStateKey(workspaceID, COMMITS_DIFF_SCOPE);

  return (
    <MasterDetailPanel workspaceId={workspaceID} stateKey={stateKey} scope={COMMITS_DIFF_SCOPE} header={header}>
      <Flex direction="column" flexGrow="1" minHeight="0" overflow="hidden">
        <HistoryTabContent workspaceId={workspaceID} viewMode="flat" diffStateKey={stateKey} />
      </Flex>
    </MasterDetailPanel>
  );
};
