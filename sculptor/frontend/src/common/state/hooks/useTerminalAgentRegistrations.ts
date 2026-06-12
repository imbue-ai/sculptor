import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";

import type { TerminalAgentRegistration } from "~/api";
import { listTerminalAgentRegistrations } from "~/api";

import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";

const TERMINAL_AGENT_REGISTRATIONS_QUERY_KEY = [SCULPTOR_QUERY_KEY_PREFIX, "terminal-agent-registrations"] as const;

const fetchTerminalAgentRegistrations = async (signal: AbortSignal): Promise<Array<TerminalAgentRegistration>> => {
  // Plain read: skip the request tracker's WS-ack wait (this endpoint never
  // publishes a stream update to acknowledge).
  const { data } = await listTerminalAgentRegistrations({ meta: { signal, skipWsAck: true } });
  return data?.registrations ?? [];
};

/**
 * Fetch the current terminal-agent registrations.
 *
 * Callers invoke `refresh` when their menu/select opens so the entries track
 * the registrations directory without a restart — the backend re-reads the
 * directory per request, and `staleTime: 0` makes each `refresh` re-fetch.
 * Going through TanStack Query gives a single shared cache across call sites,
 * in-flight de-duplication, and automatic request cancellation on unmount.
 */
export const useTerminalAgentRegistrations = (): {
  registrations: Array<TerminalAgentRegistration>;
  refresh: () => void;
} => {
  const { data, refetch } = useQuery({
    queryKey: TERMINAL_AGENT_REGISTRATIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchTerminalAgentRegistrations(signal),
    staleTime: 0,
    retry: false,
  });
  const refresh = useCallback((): void => {
    void refetch();
  }, [refetch]);
  return { registrations: data ?? [], refresh };
};
