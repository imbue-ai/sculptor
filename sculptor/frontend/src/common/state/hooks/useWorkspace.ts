import { useAtomValue } from "jotai";

import type { Workspace } from "../../../api";
import { asLiveWorkspace, workspaceAtomFamily, workspaceIdsAtom } from "../atoms/workspaces";

/**
 * Hook to access workspace data by ID.
 * Returns null if workspace is not loaded (or is a deleting tombstone) or
 * workspaceId is null/undefined.
 */
export const useWorkspace = (workspaceId: string | null | undefined): Workspace | null => {
  const workspace = asLiveWorkspace(useAtomValue(workspaceAtomFamily(workspaceId ?? "")));

  if (!workspaceId) {
    return null;
  }

  return workspace;
};

/**
 * Hook to detect whether a task's workspace has been deleted.
 * Returns false while workspaces are still loading (avoids false positives on initial page load).
 */
export const useIsWorkspaceDeleted = (workspaceId: string | null): boolean => {
  const workspace = useWorkspace(workspaceId);
  const workspaceIds = useAtomValue(workspaceIdsAtom);
  if (workspaceId === null) {
    return false;
  }

  // If workspaces haven't loaded yet, don't report as deleted
  if (workspaceIds === undefined) {
    return false;
  }
  return workspace === null;
};
