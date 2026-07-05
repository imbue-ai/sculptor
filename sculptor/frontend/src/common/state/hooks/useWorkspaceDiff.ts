import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";

import type { DiffArtifact } from "../../../api";
import { DiffStatus, getWorkspaceDiff } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../queryClient.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "../queryClient.ts";
import { useWorkspace } from "./useWorkspace";

type UseWorkspaceDiffResult = BackendQueryResult<DiffArtifact | null | undefined> & {
  /** True while the backend is recomputing the diff (`diff_status` is GENERATING). */
  isGenerating: boolean;
};

const workspaceDiffQueryKey = (workspaceId: string | null, targetBranch: string | null): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git", "diff", targetBranch] as const,
  isValid: workspaceId !== null,
});

const fetchDiff = async (
  workspaceId: string,
  signal: AbortSignal,
  forceRefresh: boolean = false,
): Promise<DiffArtifact | null> => {
  const { data } = await getWorkspaceDiff({
    path: { workspace_id: workspaceId },
    query: { scope: "vs-target-branch", ...(forceRefresh ? { force_refresh: true } : {}) },
    meta: { signal },
  });
  return data?.diff ?? null;
};

/**
 * Subscribe to the workspace diff. Always fetches with `scope=vs-target-branch`
 * so both `uncommittedDiff` and `targetBranchDiff` are available to consumers.
 *
 * The query is keyed on `targetBranch` so switching the target branch starts
 * a fresh entry (no stale data flash). Refreshes are driven by the unified
 * WebSocket stream — see `useUnifiedStream`.
 */
export const useWorkspaceDiff = (workspaceId: string | null): UseWorkspaceDiffResult => {
  const workspace = useWorkspace(workspaceId);
  const targetBranch = workspace?.targetBranch ?? null;
  const isReady = workspace?.diffStatus === DiffStatus.READY;
  const isGenerating = workspace?.diffStatus === DiffStatus.GENERATING;

  const { key, isValid } = workspaceDiffQueryKey(workspaceId, targetBranch);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchDiff(workspaceId!, signal),
    enabled: isValid && isReady,
  });

  return {
    data: query.data,
    isPending: query.isPending,
    isFetching: query.isFetching,
    isGenerating,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};

/**
 * Force a fresh diff fetch from the backend, bypassing any backend-side cache.
 *
 * Goes through `queryClient.fetchQuery` (rather than a manual fetch +
 * `setQueryData`) so any active `useWorkspaceDiff` observer sees `isFetching`
 * flip to true while the request is in flight. The `staleTime: 0` override
 * forces a fetch even though our default `staleTime` is `Infinity`.
 *
 * Use this from non-component contexts (e.g. a Jotai action). Components
 * should prefer the `useForceRefreshWorkspaceDiff` hook.
 */
export const forceRefreshWorkspaceDiff = async (workspaceId: string, targetBranch: string | null): Promise<void> => {
  await queryClient.fetchQuery({
    queryKey: workspaceDiffQueryKey(workspaceId, targetBranch).key,
    queryFn: ({ signal }) => fetchDiff(workspaceId, signal, true),
    staleTime: 0,
  });
};

/**
 * Hook variant of `forceRefreshWorkspaceDiff` for components that already
 * have a `workspaceId` in scope. Reads `targetBranch` internally so callers
 * don't need to thread cache or workspace state through the call site.
 */
export const useForceRefreshWorkspaceDiff = (workspaceId: string): (() => Promise<void>) => {
  const workspace = useWorkspace(workspaceId);
  const targetBranch = workspace?.targetBranch ?? null;
  return useCallback(() => forceRefreshWorkspaceDiff(workspaceId, targetBranch), [workspaceId, targetBranch]);
};

/**
 * Synchronously read the cached diff for a workspace, without triggering a
 * fetch. Returns null when nothing is cached yet (e.g. no observer has
 * mounted `useWorkspaceDiff` for this workspace + target branch).
 *
 * For use from non-component contexts (e.g. a Jotai action or a runtime
 * callback). Components should prefer `useWorkspaceDiff` so they re-render
 * when the data lands.
 */
export const getCachedWorkspaceDiff = (workspaceId: string, targetBranch: string | null): DiffArtifact | null => {
  return queryClient.getQueryData<DiffArtifact | null>(workspaceDiffQueryKey(workspaceId, targetBranch).key) ?? null;
};
