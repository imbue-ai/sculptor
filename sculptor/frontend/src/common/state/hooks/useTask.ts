import { useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../../api";
import { taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";

/**
 * Subscribe to a single agent task from the TanStack Query cache, populated
 * by the WS bridge (`syncTasksToQueryCache`) on every `taskViewsByTaskId` frame.
 *
 * `queryFn` is a no-op: the cache is fed entirely by WebSocket pushes, not
 * network fetches. With `staleTime: Infinity` the no-op never fires unless
 * the cache is empty on mount, in which case `useTask` returns `null`.
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
 * Subscribe to the ordered list of non-deleted task ids, populated by the WS
 * bridge. Returns `undefined` until the first frame arrives so consumers can
 * distinguish "still loading" from "no tasks".
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
