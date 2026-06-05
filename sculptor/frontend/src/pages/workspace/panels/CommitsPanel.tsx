import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { HistoryTabContent } from "./historyPanel/HistoryTabContent.tsx";

/** "Commits" panel — commit history (REQ-PANEL-1). */
export const CommitsPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();

  if (!workspaceID) return null;

  return (
    <Flex direction="column" height="100%" overflow="hidden">
      <HistoryTabContent workspaceId={workspaceID} viewMode="flat" />
    </Flex>
  );
};
