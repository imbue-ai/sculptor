import { skipToken, useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../../api";
import { agentIdsQueryKey, agentQueryKey } from "../queryClient.ts";

/**
 * Subscribe to a single agent from the TanStack Query cache, populated by the
 * WS bridge (`syncAgentsToQueryCache`) on every `taskViewsByTaskId` frame.
 * `skipToken` makes the query subscription-only — it never fetches, because
 * the cache is fed entirely by WebSocket pushes. Entries are pinned
 * (`gcTime: Infinity`) so a quiet agent can't be evicted between delta frames.
 *
 * Returns `null` for a deleted agent (tombstoned by the bridge) and for an
 * agent the stream hasn't delivered.
 */
export const useAgent = (agentId: string): CodingAgentTaskView | null => {
  const { data } = useQuery<CodingAgentTaskView | null>({
    queryKey: agentQueryKey(agentId),
    queryFn: skipToken,
  });
  return data ?? null;
};

/**
 * Subscribe to the ordered list of non-deleted agent ids, populated by the WS
 * bridge. Returns `undefined` until the first frame arrives so consumers can
 * distinguish "still loading" from "no agents".
 */
export const useAgentIds = (): ReadonlyArray<string> | undefined => {
  const { data } = useQuery<ReadonlyArray<string>>({
    queryKey: agentIdsQueryKey(),
    queryFn: skipToken,
  });
  return data;
};
