import { useQuery } from "@tanstack/react-query";

import type { AuthenticatedProviderEntry } from "~/api";
import { getPiAuthenticatedProviders } from "~/api";

import type { BackendQueryResult } from "../../queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";

const PI_AUTHENTICATED_PROVIDERS_QUERY_KEY = [SCULPTOR_QUERY_KEY_PREFIX, "pi", "authenticated-providers"] as const;

const fetchPiAuthenticatedProviders = async (signal: AbortSignal): Promise<Array<AuthenticatedProviderEntry>> => {
  // Plain global read: skip the request tracker's WS-ack wait (this endpoint
  // never publishes a stream update to acknowledge).
  const { data } = await getPiAuthenticatedProviders({ meta: { signal, skipWsAck: true } });
  return data?.providers ?? [];
};

type UsePiAuthenticatedProvidersResult = BackendQueryResult<Array<AuthenticatedProviderEntry> | undefined> & {
  /** `data ?? []` — the Providers rail renders from an empty list while loading. */
  providers: Array<AuthenticatedProviderEntry>;
};

/**
 * Fetch the pi provider catalog crossed with current authentication status.
 *
 * Global (no workspace/agent) read of process-level auth.json + env. The
 * credential-change flow (the interactive login/logout modal closing) calls
 * `refetch` so the rail tracks the new auth.json without a restart; `staleTime: 0`
 * makes each `refetch` re-fetch. Going through TanStack Query gives a single shared
 * cache, in-flight de-duplication, and request cancellation on unmount.
 */
export const usePiAuthenticatedProviders = (): UsePiAuthenticatedProvidersResult => {
  const query = useQuery({
    queryKey: PI_AUTHENTICATED_PROVIDERS_QUERY_KEY,
    queryFn: ({ signal }) => fetchPiAuthenticatedProviders(signal),
    staleTime: 0,
    retry: false,
  });
  return {
    data: query.data,
    providers: query.data ?? [],
    isPending: query.isPending,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};
