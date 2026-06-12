import { useQuery } from "@tanstack/react-query";

import type { ReadFileAtRefResponse } from "../../../api";
import { workspaceReadFile, workspaceReadFileAtRef } from "../../../api";
import type { BackendQueryKeyResult, BackendQueryResult } from "../../queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";

export type WorkspaceFilePayload = ReadFileAtRefResponse;

const workspaceFileContentQueryKey = (
  workspaceId: string | null,
  filePath: string | null,
  gitRef: string | null,
): BackendQueryKeyResult => ({
  key: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git", "fileContent", filePath, gitRef] as const,
  isValid: workspaceId !== null && filePath !== null,
});

const fetchWorkspaceFile = async (
  workspaceId: string,
  filePath: string,
  signal: AbortSignal,
): Promise<WorkspaceFilePayload | null> => {
  const { data } = await workspaceReadFile({
    path: { workspace_id: workspaceId },
    body: { filePath },
    meta: { signal },
  });
  return data ?? null;
};

const fetchWorkspaceFileAtRef = async (
  workspaceId: string,
  filePath: string,
  gitRef: string,
  signal: AbortSignal,
): Promise<WorkspaceFilePayload | null> => {
  const { data } = await workspaceReadFileAtRef({
    path: { workspace_id: workspaceId },
    body: { path: filePath, gitRef },
    meta: { signal },
  });
  return data ?? null;
};

const fetchPayload = (
  workspaceId: string,
  filePath: string,
  gitRef: string | null,
  signal: AbortSignal,
): Promise<WorkspaceFilePayload | null> => {
  if (gitRef === null) {
    return fetchWorkspaceFile(workspaceId, filePath, signal);
  }
  return fetchWorkspaceFileAtRef(workspaceId, filePath, gitRef, signal);
};

/**
 * Subscribe to a workspace file's text content (utf-8 only).
 *
 * When `gitRef` is provided, fetches the file at that ref via
 * `workspaceReadFileAtRef`. When omitted, fetches the working-directory copy
 * via `workspaceReadFile`. The query is keyed on `(workspaceId, filePath,
 * gitRef)` so the same file at the same ref is shared across all observers
 * (e.g. the diff panel + the combined diff view rendering the same hunk).
 *
 * Non-utf8 (binary) payloads resolve to `content: undefined`; use
 * `useWorkspaceFilePayload` for image/binary previews.
 *
 * Refreshes are driven by the unified WebSocket stream: when `diffUpdatedAt`
 * changes, `invalidateWorkspaceGitQueries` invalidates every cached entry
 * for the workspace. This is conservative — content pinned to an immutable
 * commit hash doesn't change — but it matches the simpler
 * "single trigger for all git-derived state" model the rest of the
 * workspace queries follow.
 */
export const useWorkspaceFileContent = (
  workspaceId: string | null,
  filePath: string | null,
  gitRef: string | null,
): BackendQueryResult<string | undefined> => {
  const { key, isValid } = workspaceFileContentQueryKey(workspaceId, filePath, gitRef);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchPayload(workspaceId!, filePath!, gitRef, signal),
    enabled: isValid,
    select: (data) => (data?.encoding === "utf-8" ? data.content : undefined),
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
 * Subscribe to a workspace file's raw payload (content + encoding). Shares
 * the same cache key as `useWorkspaceFileContent`, so text and binary
 * observers of the same file dedupe to one network fetch.
 */
export const useWorkspaceFilePayload = (
  workspaceId: string | null,
  filePath: string | null,
  gitRef: string | null,
): BackendQueryResult<WorkspaceFilePayload | undefined> => {
  const { key, isValid } = workspaceFileContentQueryKey(workspaceId, filePath, gitRef);
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchPayload(workspaceId!, filePath!, gitRef, signal),
    enabled: isValid,
    select: (data) => data ?? undefined,
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
