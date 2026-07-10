import { useQuery } from "@tanstack/react-query";

import type { ModelOption, PiModelsResponse } from "~/api";
import { getPiModels } from "~/api";

import type { BackendQueryResult } from "../../queryClient.ts";
import { SCULPTOR_QUERY_KEY_PREFIX } from "../../queryClient.ts";

const PI_MODELS_QUERY_KEY = [SCULPTOR_QUERY_KEY_PREFIX, "pi", "models"] as const;

const fetchPiModels = async (signal: AbortSignal): Promise<PiModelsResponse> => {
  // Plain global read: skip the request tracker's WS-ack wait (this endpoint
  // never publishes a stream update to acknowledge).
  const { data } = await getPiModels({ meta: { signal, skipWsAck: true } });
  return data ?? { availableModels: [], defaultModel: null };
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
 * like the endpoint — a probe failure yields an empty catalog, never an error.
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
  return {
    data: query.data,
    availableModels: query.data?.availableModels ?? [],
    defaultModel: query.data?.defaultModel ?? null,
    isPending: query.isPending,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
};
