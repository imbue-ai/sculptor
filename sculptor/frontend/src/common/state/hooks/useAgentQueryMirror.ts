import { useStore } from "jotai";
import { useEffect } from "react";

import type { CodingAgentTaskView } from "../../../api";
import { agentAtomFamily, agentIdsAtom } from "../atoms/agents";
import { removeAgentSettings } from "../atoms/draftAgentSettings.ts";
import { agentIdsQueryKey, queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "../queryClient.ts";

type JotaiStore = ReturnType<typeof useStore>;

const projectAgent = (store: JotaiStore, agentId: string, data: CodingAgentTaskView | null | undefined): void => {
  if (data === undefined) {
    // No value written yet (e.g. a subscription-only query built by useAgent
    // before the stream has delivered the agent) — nothing to project.
    return;
  }

  if (data === null) {
    // Run before the same-value guard: an agent deleted in the initial dump
    // after a reload still has persisted per-agent settings to drop.
    removeAgentSettings(agentId);
  }

  if (!Object.is(store.get(agentAtomFamily(agentId)), data)) {
    store.set(agentAtomFamily(agentId), data);
  }
};

const projectAgentIds = (store: JotaiStore, data: ReadonlyArray<string> | undefined): void => {
  if (data !== undefined && !Object.is(store.get(agentIdsAtom), data)) {
    store.set(agentIdsAtom, data);
  }
};

/**
 * One-way projection of agent state from the TanStack Query cache into the
 * legacy Jotai atoms (`agentAtomFamily` / `agentIdsAtom`).
 *
 * The query cache is the single written store for agent state — the WS bridge
 * writes authoritative frames, mutation hooks write optimistic updates — and
 * this mirror keeps the remaining Jotai readers (`agentsArrayAtom`, the
 * per-field selector families) consistent without any writer having to know
 * about both stores. Cache notifications fire synchronously inside
 * `setQueryData`, so Jotai readers never lag the cache within a tick.
 *
 * Structural sharing in the cache keeps unchanged agents referentially
 * identical, so the `Object.is` guards make repeated frames free for Jotai
 * subscribers.
 *
 * Mounted by `useUnifiedStream`, so every stream owner projects its own
 * frames. Seeding on mount covers hand-offs between stream owners; a brief
 * double-mount is harmless because projection is idempotent.
 *
 * Delete this hook (and the agent atoms) once the last Jotai reader is
 * migrated to `useAgent`/`useAgentIds`.
 */
export const useAgentQueryMirror = (): void => {
  const store = useStore();
  useEffect(() => {
    // Seed from whatever the cache already holds, so a (re)mount after frames
    // have arrived — e.g. React StrictMode's remount — starts consistent.
    queryClient
      .getQueriesData<CodingAgentTaskView | null>({ queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "agent"] })
      .forEach(([key, data]) => projectAgent(store, key[2] as string, data));
    projectAgentIds(store, queryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey()));

    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") {
        return;
      }
      const key = event.query.queryKey;
      if (key[0] !== SCULPTOR_QUERY_KEY_PREFIX) {
        return;
      }

      if (key[1] === "agent" && key.length === 3) {
        projectAgent(store, key[2] as string, event.query.state.data as CodingAgentTaskView | null | undefined);
      } else if (key[1] === "agentIds") {
        projectAgentIds(store, event.query.state.data as ReadonlyArray<string> | undefined);
      }
    });
  }, [store]);
};
