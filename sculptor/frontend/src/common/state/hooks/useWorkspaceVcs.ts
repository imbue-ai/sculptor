import type { WorkspaceVcs } from "~/common/utils/workspaceVcs.ts";
import { workspaceVcsOf } from "~/common/utils/workspaceVcs.ts";

import { useWorkspace } from "./useWorkspace.ts";

/** The version control a workspace uses; git until the workspace has streamed in. */
export const useWorkspaceVcs = (workspaceId: string | null): WorkspaceVcs => {
  const workspace = useWorkspace(workspaceId);
  return workspace === null ? "git" : workspaceVcsOf(workspace);
};
