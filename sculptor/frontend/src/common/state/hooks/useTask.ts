import { skipToken, useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../../api";
import { taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";

/**
 * Subscribe to a single agent task from the TanStack Query cache, populated
 * by the WS bridge (`syncTasksToQueryCache`) on every `taskViewsByTaskId`
 * frame. `skipToken` makes the query subscription-only — it never fetches,
 * because the cache is fed entirely by WebSocket pushes. Entries are pinned
 * (`gcTime: Infinity`) so a quiet task can't be evicted between delta frames.
 *
 * Returns `null` for a deleted task (tombstoned by the bridge) and for a task
 * the stream hasn't delivered.
 */
export const useTask = (taskId: string): CodingAgentTaskView | null => {
  const { data } = useQuery<CodingAgentTaskView | null>({
    queryKey: taskQueryKey(taskId),
    queryFn: skipToken,
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
    queryFn: skipToken,
  });
  return data;
};
