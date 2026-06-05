import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import { fileBrowserStateAtomFamily } from "./fileBrowser/atoms.ts";
import { ChangesTabContent } from "./fileBrowser/ChangesTabContent.tsx";

/** "Changes" panel — uncommitted / vs-target-branch changes (REQ-PANEL-1). */
export const ChangesPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const fileBrowserState = useAtomValue(fileBrowserStateAtomFamily(workspaceID ?? ""));

  if (!workspaceID) return null;

  return (
    <Flex direction="column" height="100%" overflow="hidden">
      <ChangesTabContent workspaceId={workspaceID} viewMode={fileBrowserState.viewMode} />
    </Flex>
  );
};
