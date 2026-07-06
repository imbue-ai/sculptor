import { useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../../api";
import { taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";

/**
 * Subscribe to a single agent task from the TanStack Query cache. The cache is
 * the single source of truth, written by the WS bridge (`syncTasksToQueryCache`
 * in `useUnifiedStream`) whenever a `taskViewsByTaskId` frame arrives.
 *
 * `queryFn` is a no-op resolver: the cache is populated entirely by WebSocket
 * pushes, not by network fetches. The `staleTime: Infinity` default on the
 * shared `queryClient` means the no-op resolver never fires unless the cache is
 * empty on mount — in which case it returns `null`.
 *
 * This replaces `useAtomValue(taskAtomFamily(id))` callers. During Phase 1 of
 * the TanStack Query migration the Jotai atom and this hook are both populated
 * by the WS bridge; callers switch over in Phase 2 (mutations) and Phase 3
 * (reads).
 */
export const useTask = (taskId: string): CodingAgentTaskView | null => {
  const { data } = useQuery<CodingAgentTaskView | null>({
    queryKey: taskQueryKey(taskId),
    queryFn: (): CodingAgentTaskView | null => null,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return data ?? null;
};

/**
 * Subscribe to the ordered list of non-deleted task ids. Mirrors `taskIdsAtom`
 * — populated by the WS bridge, not by a network fetch.
 *
 * Returns `undefined` until the first WS frame has been processed, matching the
 * atom's semantics so consumers can distinguish "still loading" from "no tasks".
 */
export const useTaskIds = (): ReadonlyArray<string> | undefined => {
  const { data } = useQuery<ReadonlyArray<string>>({
    queryKey: taskIdsQueryKey(),
    queryFn: (): ReadonlyArray<string> => [],
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return data;
};
