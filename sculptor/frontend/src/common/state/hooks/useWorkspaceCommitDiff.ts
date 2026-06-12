import { useQuery } from "@tanstack/react-query";

import { getWorkspaceCommitDiff } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../../queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";

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
