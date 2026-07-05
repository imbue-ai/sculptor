import { useQuery } from "@tanstack/react-query";

import { getCloneDefaults } from "~/api";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";

/**
 * The backend's default clones parent dir (`<sculptor_folder>/repos`). Only the
 * backend knows the real sculptor folder, which varies by deployment (dev /
 * packaged / hosted), so the Add Repository dialog reads it from here to build
 * its default Target Folder.
 *
 * It's session-constant, so we fetch it once and keep it forever (no refetch).
 * Works in both the main app and onboarding (neither has the WS stream
 * connected at the point the dialog opens). Returns `undefined` until the first
 * fetch resolves.
 */
export const useCloneDefaults = (): { defaultClonesDir: string | undefined } => {
  const { data } = useQuery({
    queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "cloneDefaults"] as const,
    queryFn: async () => {
      // skipWsAck: this read-only config endpoint opens no data-model
      // transaction, so it never emits the WS ack the SDK waits on by default.
      const response = await getCloneDefaults({ meta: { skipWsAck: true } });
      return response.data ?? null;
    },
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return { defaultClonesDir: data?.defaultClonesDir };
};
