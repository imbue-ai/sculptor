import { useQuery } from "@tanstack/react-query";

import type { ModelOption, PiModelsResponse } from "~/api";
import { getPiModels } from "~/api";

import type { BackendQueryResult } from "../../queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";

const PI_MODELS_QUERY_KEY = [SCULPTOR_QUERY_KEY_PREFIX, "pi", "models"] as const;

// One stable identity for "no catalog", shared by every errored render.
const EMPTY_PI_CATALOG: PiModelsResponse = { availableModels: [], defaultModel: null };

const fetchPiModels = async (signal: AbortSignal): Promise<PiModelsResponse> => {
  // Plain global read: skip the request tracker's WS-ack wait (this endpoint
  // never publishes a stream update to acknowledge).
  const { data } = await getPiModels({ meta: { signal, skipWsAck: true } });
  return data;
};

type UsePiModelsResult = BackendQueryResult<PiModelsResponse | undefined> & {
  /** `data?.availableModels ?? []` — the picker renders from an empty list while resolving. */
  availableModels: ReadonlyArray<ModelOption>;
  /** pi's own current model when usable, else null — the picker preselects it. */
  defaultModel: ModelOption | null;
};

/**
 * Fetch pi's curated, authenticated-only model catalog probed on the host — the
 * pre-workspace twin of the in-task catalog, feeding the New Workspace modal's
 * pi model picker.
 *
 * `enabled` gates the fetch on pi actually being the selected agent type, so the
 * probe (a short-lived pi subprocess) runs only when the picker is on screen and
 * its latency hides behind the user typing a prompt. There is no server-side
 * cache to invalidate, so freshness is client-driven: `staleTime: 0` plus a
 * window-focus refetch means a login round-trip through Settings → Pi is picked
 * up when focus returns, without stranding a stale empty catalog. Best-effort
 * like the endpoint — a fetch failure with nothing cached resolves to the empty
 * catalog (the picker's empty state, not a loading state nothing advances),
 * while a failed refetch keeps the last-known catalog.
 */
export const usePiModels = ({ enabled }: { enabled: boolean }): UsePiModelsResult => {
  const query = useQuery({
    queryKey: PI_MODELS_QUERY_KEY,
    queryFn: ({ signal }) => fetchPiModels(signal),
    enabled,
    staleTime: 0,
    refetchOnWindowFocus: true,
    retry: false,
  });
  // `data === undefined` means exactly "not resolved yet": TanStack retains the
  // last-good data across a failed refetch, so the empty-catalog fold engages
  // only when a fetch fails with nothing cached.
  const data = query.data ?? (query.isError ? EMPTY_PI_CATALOG : undefined);
  return {
    data,
    availableModels: data?.availableModels ?? [],
    defaultModel: data?.defaultModel ?? null,
    isPending: query.isPending,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};
