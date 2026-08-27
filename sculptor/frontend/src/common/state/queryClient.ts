import type { QueryKey } from "@tanstack/react-query";
import { QueryClient } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../api";

/**
 * The shared TanStack Query client.
 *
 * Server data freshness is driven by the unified WebSocket stream — when the
 * backend pushes a relevant change, we explicitly invalidate the corresponding
 * query. We pair `staleTime: Infinity` (so data is never *automatically*
 * stale) with the default `refetchOnMount: true` (so an observer mounting on
 * a query that was *explicitly* invalidated while unobserved — e.g. a tab
 * regaining focus after an agent commit invalidated its caches — picks up
 * the fresh data on first paint). Window-focus and reconnect refetches are
 * off because the WS stream covers those.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: Infinity,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      retry: 1,
    },
  },
});

// Expose the singleton on `window` so it's reachable from devtools — inspect
// the cache via `__TANSTACK_QUERY_CLIENT__.getQueryCache().getAll()`, force a
// refetch with `.invalidateQueries({ queryKey: [...] })`, etc. Also lets the
// standalone React Query DevTools panel auto-discover the client.
declare global {
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions -- interface merging is required to augment the global Window type
  interface Window {
    __TANSTACK_QUERY_CLIENT__: QueryClient;
  }
}
window.__TANSTACK_QUERY_CLIENT__ = queryClient;

/**
 * Reserved first element for every host-owned query key.
 *
 * This `queryClient` is shared with runtime-loaded extensions through an
 * import map, so the key space is partitioned by namespace: host queries live
 * under `["sculptor", …]`, while each extension keys its queries under its own
 * extension id. Keeping the host's keys behind this prefix guarantees an extension can
 * never collide with — or accidentally invalidate — a host query, and vice
 * versa. Every host query key MUST start with this constant.
 */
export const SCULPTOR_QUERY_KEY_PREFIX = "sculptor";

/**
 * Query keys for all workspace-scoped queries share the prefix
 * `["sculptor", "workspace", workspaceId, …]`. Git-derived caches (diff, files,
 * commits, file content) are grouped one level deeper under `"git"` so the
 * diff-update cascade can invalidate just that subtree, leaving any future
 * non-git workspace queries (e.g. PR status) untouched.
 *
 *   ["sculptor", "workspace", id]                 ← whole-workspace scope (close/delete)
 *   ["sculptor", "workspace", id, "git"]          ← git-derived scope (diffUpdatedAt cascade)
 *   ["sculptor", "workspace", id, "git", "diff", ...]
 *   ["sculptor", "workspace", id, "git", "files"]
 *   ["sculptor", "workspace", id, "git", "commits", targetBranch]
 *   ["sculptor", "workspace", id, "git", "fileContent", path, gitRef]
 */
export const workspaceQueryKeyPrefix = (workspaceId: string): QueryKey =>
  [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId] as const;

export const workspaceGitQueryKeyPrefix = (workspaceId: string): QueryKey =>
  [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "git"] as const;

/**
 * Query key for the Home recent-workspaces list — a pulled REST snapshot,
 * refreshed by invalidation: on workspace-membership changes from the stream
 * and on a confirmed delete (so the list heals even when the stream is down).
 */
export const recentWorkspacesQueryKey = (): ReadonlyArray<string> =>
  [SCULPTOR_QUERY_KEY_PREFIX, "recentWorkspaces"] as const;

/** Query key for a single agent by its id, populated by the WS bridge. */
export const agentQueryKey = (agentId: string): ReadonlyArray<string> =>
  [SCULPTOR_QUERY_KEY_PREFIX, "agent", agentId] as const;

/** Query key for the ordered list of non-deleted agent ids, updated by the WS bridge. */
export const agentIdsQueryKey = (): ReadonlyArray<string> => [SCULPTOR_QUERY_KEY_PREFIX, "agentIds"] as const;

// Agent entries are fed exclusively by the WS stream, which sends one full
// dump at connect and then only *changed* agents. The default 5-minute gcTime
// would evict any unobserved, quiet agent, and nothing re-delivers it until it
// next changes — so pin agent entries for the app's lifetime (like the Jotai
// atoms they replace). Deleted agents stay as tiny `null` tombstones.
queryClient.setQueryDefaults([SCULPTOR_QUERY_KEY_PREFIX, "agent"], { gcTime: Infinity });
queryClient.setQueryDefaults([SCULPTOR_QUERY_KEY_PREFIX, "agentIds"], { gcTime: Infinity });

// Monotonic count of authoritative (WS) writes per agent. Optimistic mutations
// capture it in `onMutate` and roll back in `onError` only if it is unchanged:
// if a WS frame wrote the agent while the request was in flight, the frame
// holds server truth (whether or not the mutation committed) and a snapshot
// restore would clobber it.
const agentSyncVersionByAgentId = new Map<string, number>();

export const getAgentSyncVersion = (agentId: string): number => agentSyncVersionByAgentId.get(agentId) ?? 0;

/**
 * Write a batch of agent-view updates into the query cache. Called by the WS
 * bridge (`useUnifiedStream`) on every `taskViewsByTaskId` frame (the wire
 * still says task for an agent run) — the single writer of authoritative
 * agent state. Structural sharing keeps unchanged agents referentially
 * identical, and the agent-ids list is only rewritten when ids actually
 * change (except the first frame, which writes even an empty list so
 * consumers can tell "loaded, no agents" from "still loading").
 */
export const syncAgentsToQueryCache = (agentViewsByAgentId: Record<string, CodingAgentTaskView>): void => {
  const currentIds = queryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey());
  const idSet = new Set(currentIds);
  let didIdsChange = currentIds === undefined;

  Object.entries(agentViewsByAgentId).forEach(([id, agent]) => {
    queryClient.setQueryData<CodingAgentTaskView | null>(agentQueryKey(id), agent.isDeleted ? null : agent);
    agentSyncVersionByAgentId.set(id, getAgentSyncVersion(id) + 1);

    if (agent.isDeleted) {
      if (idSet.delete(id)) {
        didIdsChange = true;
      }
    } else if (!idSet.has(id)) {
      idSet.add(id);
      didIdsChange = true;
    }
  });

  if (didIdsChange) {
    queryClient.setQueryData<ReadonlyArray<string>>(agentIdsQueryKey(), Array.from(idSet));
  }
};

/**
 * Bundle returned by every queryKey helper — workspace-scoped, project-scoped,
 * or otherwise. Pairs the cache key with `isValid`, which records whether
 * every input the key requires was non-null. Callers feed `isValid` into the
 * hook's `enabled` (composing with any extra predicates the hook needs,
 * e.g. `isValid && workspace !== null`).
 *
 * Co-locating the key and its validity check means a new required input to
 * the key forces an update to `isValid` in the same place — the call-site
 * `enabled` predicate can't drift out of sync. It also lets the key helper
 * accept `string | null` directly, so callers don't need `?? ""` fallbacks
 * or `!` type-lies.
 */
export type BackendQueryKeyResult = {
  key: QueryKey;
  isValid: boolean;
};

/**
 * Standard shape every `useQuery`-backed hook returns — workspace-scoped,
 * project-scoped, or otherwise. Keeps the status surface uniform across hooks
 * (`useWorkspaceDiff`, `useWorkspaceFiles`, `useProjectSkills`, …) so consumers
 * always know to expect `{ data, isPending, isFetching, isError, error, refetch }`.
 *
 * `isPending` is true whenever the hook has nothing to show — covering both
 * the "gated, no fetch attempted yet" window and the "first fetch in flight"
 * window. It's the right signal for "should I render a loading state?".
 * Components that need to distinguish "waiting to even start a fetch" from
 * "fetch in progress" can pair it with `isFetching`.
 *
 * Hooks with extra derived state (e.g. `isGenerating` on the diff hook)
 * intersect this with their own extension.
 */
export type BackendQueryResult<T> = {
  data: T;
  isPending: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
};

/**
 * Mark every git-derived cache for the workspace stale so any active observer
 * refetches. Triggered by the `diffUpdatedAt` WS cascade.
 */
export const invalidateWorkspaceGitQueries = (workspaceId: string): void => {
  void queryClient.invalidateQueries({ queryKey: workspaceGitQueryKeyPrefix(workspaceId) });
};

/**
 * Drop every cached query for the workspace (git-derived and otherwise). Used
 * when the workspace tab is closed or the workspace is deleted — no observer
 * should ever read this data again, so we free it.
 */
export const removeWorkspaceQueriesCache = (workspaceId: string): void => {
  queryClient.removeQueries({ queryKey: workspaceQueryKeyPrefix(workspaceId) });
};
