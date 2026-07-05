import { useQuery } from "@tanstack/react-query";

import type { RemoteRepo } from "~/api";
import { listRemoteRepos } from "~/api";
import type { BackendQueryResult } from "~/common/state/queryClient.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";

import type { RemoteProvider } from "../SourceRadioCards.tsx";

// SWR window: within this, repeat reads for the same (provider, q) are served
// from cache with no background refetch. After it, the cached value is shown
// immediately and a refetch fires in the background. Five minutes of gc buys
// "back-and-forth typing in the same session feels instant" without holding
// stale gh results forever.
const REMOTE_REPOS_STALE_TIME_MS = 60_000;
const REMOTE_REPOS_GC_TIME_MS = 5 * 60_000;

// How many rows the combobox renders for the empty-query initial list. Shared
// so prefetchers can warm the exact cache key the combobox will read.
export const REMOTE_REPOS_INITIAL_LIMIT = 5;

// gh treats search as case-insensitive, so `"Foo"` and `" foo "` share a
// cache entry. We still pass the user's typed string through to the backend
// unchanged; only the cache key is normalized.
export const normalizeQuery = (q: string): string => q.trim().toLowerCase();

// Keys live under the host's reserved `SCULPTOR_QUERY_KEY_PREFIX` namespace so
// runtime-loaded plugins keyed on the same root can't collide with this cache.
export const remoteReposQueryKey = (
  provider: RemoteProvider,
  q: string,
  limit: number,
): readonly [typeof SCULPTOR_QUERY_KEY_PREFIX, "remoteRepos", RemoteProvider, string, number] =>
  [SCULPTOR_QUERY_KEY_PREFIX, "remoteRepos", provider, normalizeQuery(q), limit] as const;

const isNotConfiguredError = (error: unknown): boolean => error instanceof HTTPException && error.status === 412;

// Retry policy for the remote-repos query. 412 means gh isn't
// installed / authenticated — retrying won't help and the combobox surfaces a
// different UI for that case. Anything else gets one retry.
export const shouldRetryRemoteRepos = (failureCount: number, error: unknown): boolean =>
  !isNotConfiguredError(error) && failureCount < 1;

// Decide whether the previous query's data should be carried forward into the
// new query. True when the previous query was for the same provider (typing
// into the combobox, or bumping the limit). Returning the predicate as a
// standalone function lets the test exercise it without rendering a React
// tree, while the inline `placeholderData` keeps TanStack's generics happy.
// The provider sits at index 2 of the key (after the prefix and "remoteRepos").
export const shouldKeepPreviousRemoteReposData = (
  provider: RemoteProvider,
  prevQueryKey: ReadonlyArray<unknown> | undefined,
): boolean => prevQueryKey?.[2] === provider;

const fetchRemoteRepos = async (
  provider: RemoteProvider,
  q: string,
  limit: number,
  signal?: AbortSignal,
): Promise<ReadonlyArray<RemoteRepo>> => {
  const { data } = await listRemoteRepos({
    path: { provider },
    query: { q: q || undefined, limit },
    // skipWsAck: this read-only endpoint shells out to gh and never opens
    // a data-model transaction, so it doesn't emit the WS ack the SDK waits
    // on. Without this, the request times out at 10s.
    meta: { signal, skipWsAck: true },
  });
  return data ?? [];
};

// Warm the empty-query initial list cache so the combobox paints with results
// on first mount instead of showing a spinner. Best-effort: errors (including
// 412 for unconfigured CLIs) are swallowed — the combobox will surface them
// on mount if it actually renders.
export const prefetchInitialRemoteRepos = (provider: RemoteProvider): Promise<void> =>
  queryClient
    .prefetchQuery({
      queryKey: remoteReposQueryKey(provider, "", REMOTE_REPOS_INITIAL_LIMIT),
      queryFn: ({ signal }) => fetchRemoteRepos(provider, "", REMOTE_REPOS_INITIAL_LIMIT, signal),
      staleTime: REMOTE_REPOS_STALE_TIME_MS,
      gcTime: REMOTE_REPOS_GC_TIME_MS,
    })
    .catch(() => {
      // Swallow — the hook will retry/handle on mount.
    });

export const useRemoteRepos = (
  provider: RemoteProvider,
  q: string,
  limit: number,
): BackendQueryResult<ReadonlyArray<RemoteRepo> | undefined> => {
  const query = useQuery({
    queryKey: remoteReposQueryKey(provider, q, limit),
    queryFn: ({ signal }) => fetchRemoteRepos(provider, q, limit, signal),
    staleTime: REMOTE_REPOS_STALE_TIME_MS,
    gcTime: REMOTE_REPOS_GC_TIME_MS,
    placeholderData: (prev, prevQuery) =>
      shouldKeepPreviousRemoteReposData(provider, prevQuery?.queryKey) ? prev : undefined,
    retry: shouldRetryRemoteRepos,
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
