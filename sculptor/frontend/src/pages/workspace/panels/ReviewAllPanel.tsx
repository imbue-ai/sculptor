import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { fileBrowserDiffViewTypeAtom } from "~/common/state/atoms/userConfig.ts";
import { CombinedDiffView } from "~/pages/workspace/components/diffPanel/CombinedDiffView.tsx";

/**
 * "Review All" panel — the combined multi-file diff, promoted from a tab inside
 * the single-file diff viewer to its own registered panel (REQ-CENTER-5). Add it
 * to the Left or Right section via that section's "+" dropdown.
 */
export const ReviewAllPanel = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const viewType = useAtomValue(fileBrowserDiffViewTypeAtom);

  if (!workspaceID) return null;

  return (
    <Flex direction="column" height="100%" overflow="hidden">
      <CombinedDiffView workspaceId={workspaceID} viewType={viewType} isActive />
    </Flex>
  );
};
