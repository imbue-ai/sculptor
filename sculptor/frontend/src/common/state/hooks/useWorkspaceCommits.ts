import { useQuery } from "@tanstack/react-query";

import type { CommitHistoryResponse } from "../../../api";
import { getWorkspaceCommits } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../../queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";
import { useWorkspace } from "./useWorkspace";

const workspaceCommitsQueryKey = (workspaceId: string | null, targetBranch: string | null): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git", "commits", targetBranch] as const,
  isValid: workspaceId !== null,
});

const fetchCommits = async (workspaceId: string, signal: AbortSignal): Promise<CommitHistoryResponse | null> => {
  const { data } = await getWorkspaceCommits({
    path: { workspace_id: workspaceId },
    meta: { signal },
  });
  return data ?? null;
};

/**
 * Subscribe to the workspace's commit history. The query is keyed on
 * `targetBranch` so switching the target branch (which moves the fork point)
 * starts a fresh entry without flashing stale commits. Refreshes are driven
 * by the unified WebSocket stream — `updateWorkspacesAtom` calls
 * `invalidateWorkspaceGitQueries` when `diffUpdatedAt` changes (e.g. after the
 * agent makes a new commit).
 */
export const useWorkspaceCommits = (
  workspaceId: string | null,
): BackendQueryResult<CommitHistoryResponse | null | undefined> => {
  const workspace = useWorkspace(workspaceId);
  const targetBranch = workspace?.targetBranch ?? null;

  const { key, isValid } = workspaceCommitsQueryKey(workspaceId, targetBranch);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchCommits(workspaceId!, signal),
    // Additionally gate on the workspace atom being populated so the first
    // fetch uses the real `targetBranch` (in the queryKey) instead of the
    // transient pre-hydration `null`. Otherwise the initial fetch fires with
    // key `[…, "commits", null]`, gets orphaned when the WS frame arrives
    // and flips targetBranch to "main", and a second fetch under the new
    // key fires for no actual data change. `workspace !== null` implies
    // `workspaceId` was non-null too (see `useWorkspace`), so it subsumes
    // `isValid` — kept here for symmetry with the other hooks.
    enabled: isValid && workspace !== null,
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
