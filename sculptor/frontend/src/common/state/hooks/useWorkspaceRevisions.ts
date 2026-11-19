import { useQuery } from "@tanstack/react-query";

import type { RevisionHistoryResponse } from "~/api";
import { getWorkspaceRevisions } from "~/api";
import { workspaceVcsOf } from "~/common/utils/workspaceVcs.ts";

import type { BackendQueryKeyResult, BackendQueryResult } from "../queryClient.ts";
import { workspaceRevisionsQueryKeyPrefix } from "../queryClient.ts";
import { useWorkspace } from "./useWorkspace.ts";

const workspaceRevisionsQueryKey = (
  workspaceId: string | null,
  targetBranch: string | null,
): BackendQueryKeyResult => ({
  key: [...workspaceRevisionsQueryKeyPrefix(workspaceId), targetBranch],
  isValid: workspaceId !== null,
});

const fetchRevisions = async (workspaceId: string, signal: AbortSignal): Promise<RevisionHistoryResponse | null> => {
  const { data } = await getWorkspaceRevisions({
    path: { workspace_id: workspaceId },
    meta: { signal },
  });
  return data ?? null;
};

/**
 * Subscribe to a jj workspace's revisions, newest first, back to where its
 * stack forks from its target. A git workspace has commits instead
 * (`useWorkspaceCommits`), so nothing is fetched for one. Like the commits, the
 * query is keyed on the target, which moves the fork point, and sits in the
 * workspace's VCS subtree, which the stream invalidates when `diffUpdatedAt`
 * changes.
 */
export const useWorkspaceRevisions = (
  workspaceId: string | null,
): BackendQueryResult<RevisionHistoryResponse | null | undefined> => {
  const workspace = useWorkspace(workspaceId);
  const targetBranch = workspace?.targetBranch ?? null;
  const isJjWorkspace = workspace !== null && workspaceVcsOf(workspace) === "jj";

  const { key, isValid } = workspaceRevisionsQueryKey(workspaceId, targetBranch);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchRevisions(workspaceId!, signal),
    enabled: isValid && isJjWorkspace,
  });

  return {
    data: query.data,
    isPending: query.isPending,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};
