import type { ReactElement } from "react";

import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { workspaceVcsOf } from "~/common/utils/workspaceVcs.ts";

import { GitIdentityPill } from "./GitIdentityPill.tsx";
import { JjIdentityPill } from "./JjIdentityPill.tsx";

/** What the header calls the workspace's checkout: its branch, or for jj its bookmark. */
export const WorkspaceIdentityPill = ({ workspaceId }: { workspaceId: string }): ReactElement | null => {
  const workspace = useWorkspace(workspaceId);
  if (workspace === null) {
    return null;
  }
  return workspaceVcsOf(workspace) === "jj" ? (
    <JjIdentityPill workspaceId={workspaceId} />
  ) : (
    <GitIdentityPill workspaceId={workspaceId} />
  );
};
