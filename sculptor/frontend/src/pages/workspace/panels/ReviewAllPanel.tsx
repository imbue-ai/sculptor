// The Review All panel: a single-instance panel that shows the workspace's combined
// multi-file diff. It is a thin wrapper around the proven CombinedDiffView surface —
// auto-collapse above the file-count threshold and workspace-scoped changes
// (All/Uncommitted) are preserved, not redesigned. The panel has no default section,
// so it is not opened by default; it appears only once the user adds it to a section.

import { Flex } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { fileBrowserDiffViewTypeAtom } from "~/common/state/atoms/userConfig.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import { CombinedDiffView } from "~/pages/workspace/components/diffPanel/CombinedDiffView.tsx";

const ReviewAllPanelContent = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  // The unified/split preference is shared with the single-file diff viewer.
  const viewType = useAtomValue(fileBrowserDiffViewTypeAtom);

  // CombinedDiffView fills a flex column (its wrapper uses flex: 1), so the panel
  // root is a flex column too. CombinedDiffView is built to coexist with
  // single-file tabs, so it takes an isActive flag; here it is the whole panel,
  // so it is always active.
  return (
    <Flex direction="column" flexGrow="1" minHeight="0" data-testid={ElementIds.REVIEW_ALL_PANEL}>
      <CombinedDiffView workspaceId={workspaceId} viewType={viewType} isActive />
    </Flex>
  );
};

export const ReviewAllPanel = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return null;
  }
  // Key on the workspace id so switching workspaces resets the combined diff's
  // per-file collapse state instead of carrying it across workspaces.
  return <ReviewAllPanelContent key={workspaceId} workspaceId={workspaceId} />;
};
