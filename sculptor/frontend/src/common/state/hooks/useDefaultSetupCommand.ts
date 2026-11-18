import { useQuery } from "@tanstack/react-query";

import type { WorkspaceInitializationStrategy, WorkspaceSetupCommandDefaults } from "~/api";
import { getWorkspaceSetupCommandDefaults } from "~/api";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";

type DefaultSetupCommandByKind = WorkspaceSetupCommandDefaults["defaultSetupCommandByInitializationStrategy"];

/**
 * The setup command a workspace of `kind` runs when its project configures
 * none, as that kind's version control defines it: a string, null for a kind
 * that runs no setup command, or undefined until the backend has answered.
 *
 * The defaults are session-constant, so they are fetched once and kept.
 */
export const useDefaultSetupCommand = (kind: WorkspaceInitializationStrategy): string | null | undefined => {
  const { data } = useQuery({
    queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "workspaceSetupCommandDefaults"] as const,
    queryFn: async (): Promise<DefaultSetupCommandByKind> => {
      // skipWsAck: the endpoint opens no data-model transaction, so no stream
      // acknowledgement ever follows.
      const { data: defaults } = await getWorkspaceSetupCommandDefaults({ meta: { skipWsAck: true } });
      return defaults.defaultSetupCommandByInitializationStrategy;
    },
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return data?.[kind];
};
