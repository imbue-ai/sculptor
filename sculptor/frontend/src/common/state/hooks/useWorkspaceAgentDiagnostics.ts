// Fetches per-agent diagnostics (claude session id + claude/Sculptor transcript file
// paths) for the active workspace's agents, powering the panel-tab context-menu copy
// actions. The copy items are derived from this data in dynamicPanels, so
// the session/transcript items stay disabled until a session exists and become enabled
// once the agent has run.
//
// Each agent is fetched once per (id, status) pair via a TanStack query keyed on that
// pair: an agent with no session yet returns empty diagnostics, and the refetch when its
// status changes (e.g. after the first prompt completes) picks up the now-available
// session. The result is a stable map keyed by task id, so the registry-sync hook can
// read agent.diagnostics without triggering a fetch on every task tick.

import { useQueries } from "@tanstack/react-query";
import { useCallback } from "react";

import type { TaskStatus } from "~/api";
import { getWorkspaceAgentDiagnostics } from "~/api";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/queryClient.ts";
import type { DynamicAgentDiagnostics } from "~/components/sections/registry/dynamicPanels.tsx";

export type AgentDiagnosticsTarget = { taskId: string; status: TaskStatus };

export type AgentDiagnosticsByTaskId = Readonly<Record<string, DynamicAgentDiagnostics>>;

// Diagnostics have no push/invalidation signal (the WS stream doesn't cover them), so
// data is held fresh for a finite window rather than the client-wide `staleTime: Infinity`.
// Folding `status` into the key means an agent's status change (e.g. its first prompt
// completing and a session appearing) is a fresh key — and thus a refetch — on its own,
// so this only governs the redundant-refetch window within a single status.
const AGENT_DIAGNOSTICS_STALE_TIME_MS = 30_000;

type AgentDiagnosticsQueryResult = { taskId: string; diagnostics: DynamicAgentDiagnostics | undefined };

const fetchAgentDiagnostics = async (
  workspaceId: string,
  taskId: string,
  signal: AbortSignal,
): Promise<DynamicAgentDiagnostics | undefined> => {
  const { data } = await getWorkspaceAgentDiagnostics({
    path: { workspace_id: workspaceId, agent_id: taskId },
    meta: { signal },
  });
  if (data === undefined) {
    return undefined;
  }
  return {
    sessionId: data.sessionId ?? null,
    claudeTranscriptPath: data.transcriptFilePath ?? null,
    sculptorTranscriptPath: data.sculptorTranscriptFilePath ?? null,
  };
};

export const useWorkspaceAgentDiagnostics = (
  workspaceId: string,
  targets: ReadonlyArray<AgentDiagnosticsTarget>,
): AgentDiagnosticsByTaskId => {
  // One query per agent under the workspace cascade so `removeWorkspaceQueriesCache`
  // evicts it on close. The key omits the `"git"` segment so the `diffUpdatedAt`
  // cascade doesn't needlessly invalidate it; `status` is part of the key so a status
  // change is its own fresh query (an agent with no session yet returns empty
  // diagnostics, and the refetch when its status changes picks up the now-available
  // session). `useQueries` only renders the current `targets`, so the combined map
  // can't leak entries for agents that no longer exist.
  return useQueries({
    queries: targets.map(({ taskId, status }) => ({
      queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "agentDiagnostics", taskId, status] as const,
      queryFn: ({ signal }: { signal: AbortSignal }): Promise<AgentDiagnosticsQueryResult> =>
        fetchAgentDiagnostics(workspaceId, taskId, signal).then((diagnostics) => ({ taskId, diagnostics })),
      staleTime: AGENT_DIAGNOSTICS_STALE_TIME_MS,
    })),
    // Surface a failing diagnostics endpoint instead of silently presenting it as
    // "no diagnostics yet" — `useQuery`'s native error makes a hand-rolled signal
    // unnecessary, we just have to log it.
    combine: useCallback((results: Array<{ data?: AgentDiagnosticsQueryResult; error: unknown }>) => {
      const next: Record<string, DynamicAgentDiagnostics> = {};
      for (const { data, error } of results) {
        if (error !== null) {
          console.warn("Failed to fetch workspace agent diagnostics", error);
          continue;
        }

        if (data?.diagnostics !== undefined) {
          next[data.taskId] = data.diagnostics;
        }
      }
      return next;
    }, []),
  });
};
