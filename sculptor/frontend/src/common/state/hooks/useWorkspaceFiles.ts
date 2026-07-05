import { useQuery } from "@tanstack/react-query";

import { getWorkspaceFiles } from "../../../api";
import type { FileListEntry } from "../../../pages/workspace/panels/fileBrowser/types/fileBrowser.ts";
import { HTTPException } from "../../utils/errors.ts";
import type { BackendQueryKeyResult, BackendQueryResult } from "../queryClient.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "../queryClient.ts";

// The backend returns 503 with a `Retry-After` header on transient git
// failures (e.g. index lock contention). Retry locally so the user doesn't see
// a one-shot blip become a permanent error state. Backend ownership of the
// signal is from SCU-1263.
const TRANSIENT_FAILURE_RETRIES = 4; // 5 attempts total (1 initial + 4 retries)
const TRANSIENT_FAILURE_RETRY_DELAY_MS = 500;

const workspaceFilesQueryKey = (workspaceId: string | null): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git", "files"] as const,
  isValid: workspaceId !== null,
});

const fetchFiles = async (workspaceId: string, signal: AbortSignal): Promise<ReadonlyArray<FileListEntry>> => {
  const { data } = await getWorkspaceFiles({
    path: { workspace_id: workspaceId },
    meta: { signal },
  });
  return data?.files ?? [];
};

const isTransientFileListFailure = (error: unknown): boolean => error instanceof HTTPException && error.status === 503;

/**
 * Subscribe to the workspace's file list. Refreshes are driven by the unified
 * WebSocket stream — `updateWorkspacesAtom` calls
 * `invalidateWorkspaceGitQueries` when the workspace's `diffUpdatedAt` changes.
 */
export const useWorkspaceFiles = (
  workspaceId: string | null,
): BackendQueryResult<ReadonlyArray<FileListEntry> | undefined> => {
  const { key, isValid } = workspaceFilesQueryKey(workspaceId);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchFiles(workspaceId!, signal),
    enabled: isValid,
    retry: (failureCount, error) => isTransientFileListFailure(error) && failureCount < TRANSIENT_FAILURE_RETRIES,
    retryDelay: TRANSIENT_FAILURE_RETRY_DELAY_MS,
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

/**
 * Get the cached file list for a workspace if present, otherwise fetch it.
 * Useful for non-React callers (e.g. tiptap suggestion plugins) that want to
 * piggyback on the cache populated by `useWorkspaceFiles` observers without
 * subscribing.
 */
export const ensureWorkspaceFiles = async (workspaceId: string): Promise<ReadonlyArray<FileListEntry>> => {
  return await queryClient.ensureQueryData({
    queryKey: workspaceFilesQueryKey(workspaceId).key,
    queryFn: ({ signal }) => fetchFiles(workspaceId, signal),
  });
};
