import { useQuery } from "@tanstack/react-query";

import { getWorkspaceCommitDiff } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../queryClient.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "../queryClient.ts";

/**
 * Single-commit diffs are immutable — `(workspaceId, commitHash)` permanently
 * identifies the response — so the cache key sits as a sibling of the `"git"`
 * subtree, not inside it. The `diffUpdatedAt` invalidation cascade would
 * otherwise trigger refetches that return byte-identical data.
 * Workspace-close cleanup still wipes it because `removeWorkspaceQueriesCache`
 * targets the whole `["sculptor", "workspace", workspaceId]` prefix.
 */
const workspaceCommitDiffQueryKey = (workspaceId: string | null, commitHash: string | null): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "commitDiff", commitHash] as const,
  isValid: workspaceId !== null && commitHash !== null,
});

/**
 * Invalidate the cached diff for a single commit so an active observer refetches.
 * Commit diffs are keyed OUTSIDE the `"git"` subtree, so the workspace git-query
 * invalidation cascade never reaches them; a manual refresh has to target this
 * key directly. Useful when the original fetch failed (e.g. the workspace was
 * still initializing) and the viewer needs a way to retry.
 */
export const invalidateWorkspaceCommitDiff = (workspaceId: string, commitHash: string): void => {
  const { key } = workspaceCommitDiffQueryKey(workspaceId, commitHash);
  void queryClient.invalidateQueries({ queryKey: key });
};

const fetchCommitDiff = async (workspaceId: string, commitHash: string, signal: AbortSignal): Promise<string> => {
  const { data } = await getWorkspaceCommitDiff({
    path: { workspace_id: workspaceId },
    query: { commit_hash: commitHash },
    meta: { signal },
  });
  return data?.diff ?? "";
};

/**
 * Subscribe to the unified diff for a single commit.
 *
 * The query is keyed on `(workspaceId, commitHash)`. Git commit hashes are
 * immutable identifiers (the backend rejects anything non-hex and resolves to
 * a canonical 40-char SHA), so the cached diff never goes stale — switching
 * away from a commit-diff tab and back is a guaranteed cache hit.
 */
export const useWorkspaceCommitDiff = (
  workspaceId: string | null,
  commitHash: string | null,
): BackendQueryResult<string | undefined> => {
  const { key, isValid } = workspaceCommitDiffQueryKey(workspaceId, commitHash);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchCommitDiff(workspaceId!, commitHash!, signal),
    enabled: isValid,
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
