import { useStore } from "jotai";
import { useEffect } from "react";

import type { CodingAgentTaskView } from "../../../api";
import { agentAtomFamily, agentIdsAtom } from "../atoms/agents";
import { removeAgentSettings } from "../atoms/draftAgentSettings.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX, taskIdsQueryKey } from "../queryClient.ts";

type JotaiStore = ReturnType<typeof useStore>;

const projectTask = (store: JotaiStore, taskId: string, data: CodingAgentTaskView | null | undefined): void => {
  if (data === undefined) {
    // No value written yet (e.g. a subscription-only query built by useTask
    // before the stream has delivered the task) — nothing to project.
    return;
  }

  if (data === null) {
    // Run before the same-value guard: a task deleted in the initial dump
    // after a reload still has persisted per-agent settings to drop.
    removeAgentSettings(taskId);
  }

  if (!Object.is(store.get(agentAtomFamily(taskId)), data)) {
    store.set(agentAtomFamily(taskId), data);
  }
};

const projectTaskIds = (store: JotaiStore, data: ReadonlyArray<string> | undefined): void => {
  if (data !== undefined && !Object.is(store.get(agentIdsAtom), data)) {
    store.set(agentIdsAtom, data);
  }
};

/**
 * One-way projection of agent-task state from the TanStack Query cache into
 * the legacy Jotai atoms (`agentAtomFamily` / `agentIdsAtom`).
 *
 * The query cache is the single written store for task state — the WS bridge
 * writes authoritative frames, mutation hooks write optimistic updates — and
 * this mirror keeps the remaining Jotai readers (`agentsArrayAtom`, the
 * per-field selector families) consistent without any writer having to know
 * about both stores. Cache notifications fire synchronously inside
 * `setQueryData`, so Jotai readers never lag the cache within a tick.
 *
 * Structural sharing in the cache keeps unchanged tasks referentially
 * identical, so the `Object.is` guards make repeated frames free for Jotai
 * subscribers.
 *
 * Mounted by `useUnifiedStream`, so every stream owner projects its own
 * frames. Seeding on mount covers hand-offs between stream owners; a brief
 * double-mount is harmless because projection is idempotent.
 *
 * Delete this hook (and the task atoms) once the last Jotai reader is
 * migrated to `useTask`/`useTaskIds`.
 */
export const useTaskQueryMirror = (): void => {
  const store = useStore();
  useEffect(() => {
    // Seed from whatever the cache already holds, so a (re)mount after frames
    // have arrived — e.g. React StrictMode's remount — starts consistent.
    queryClient
      .getQueriesData<CodingAgentTaskView | null>({ queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "task"] })
      .forEach(([key, data]) => projectTask(store, key[2] as string, data));
    projectTaskIds(store, queryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey()));

    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") {
        return;
      }
      const key = event.query.queryKey;
      if (key[0] !== SCULPTOR_QUERY_KEY_PREFIX) {
        return;
      }

      if (key[1] === "task" && key.length === 3) {
        projectTask(store, key[2] as string, event.query.state.data as CodingAgentTaskView | null | undefined);
      } else if (key[1] === "taskIds") {
        projectTaskIds(store, event.query.state.data as ReadonlyArray<string> | undefined);
      }
    });
  }, [store]);
};
