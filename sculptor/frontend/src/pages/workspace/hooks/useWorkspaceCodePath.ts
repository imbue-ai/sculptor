import { useAtomValue } from "jotai";

import { WorkspaceInitializationStrategy } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { repoInfoAtomFamily } from "~/common/state/atoms/repoInfo.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";

/**
 * Returns the absolute path of the code directory for a workspace.
 *
 * IN_PLACE workspaces work directly in the user's repo, so they use the
 * repo path from RepoInfo. Every other strategy owns its own checkout at
 * `${environmentId}/code`.
 * Returns null if the information is not yet available.
 *
 * When called without arguments, uses the workspace ID from the current URL.
 * Pass an explicit `workspaceId` to look up a specific workspace.
 *
 * TODO: The backend should expose the code path directly on the workspace
 * object so the frontend doesn't need to re-derive it from environmentId /
 * repoPath.
 */
export const useWorkspaceCodePath = (workspaceId?: string): string | null => {
  const { workspaceID: workspaceIdFromParams } = useWorkspacePageParams();
  const resolvedWorkspaceId = workspaceId ?? workspaceIdFromParams;
  const workspace = useWorkspace(resolvedWorkspaceId);

  const projectId = workspace?.projectId ?? "";
  const repoInfo = useAtomValue(repoInfoAtomFamily(projectId));

  if (!workspace) {
    return null;
  }

  if (workspace.initializationStrategy === WorkspaceInitializationStrategy.IN_PLACE) {
    return repoInfo?.repoPath ?? null;
  }

  return workspace.environmentId ? `${workspace.environmentId}/code` : null;
};
