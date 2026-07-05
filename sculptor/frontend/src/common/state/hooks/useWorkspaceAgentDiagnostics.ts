// Fetches per-agent diagnostics (claude session id + claude/Sculptor transcript file
// paths) for the active workspace's agents, powering the panel-tab context-menu copy
// actions. The copy items are derived from this data in dynamicPanels, so
// the session/transcript items stay disabled until a session exists and become enabled
// once the agent has run.
//
// Each agent has ONE query keyed by (workspace, task). A task's status is not part of
// the key — it is an invalidation signal: when a task's status changes (e.g. its first
// prompt completing and a session appearing), the effect below explicitly invalidates
// that task's query, which refetches while continuing to serve the previous data. The
// result is a stable map keyed by task id, so the registry-sync hook can read
// agent.diagnostics without triggering a fetch on every task tick.
//
// Do NOT fold `status` into the query key instead. A task view can transiently derive
// READY before its messages load, caching (task, READY) with empty diagnostics; the
// RUNNING→READY flip at the end of the first run then lands on that cached entry, and —
// with window-focus/reconnect refetches disabled client-wide — nothing ever refetches
// it, leaving the copy items disabled forever.

import { useQueries, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import type { TaskStatus } from "~/api";
import { getWorkspaceAgentDiagnostics } from "~/api";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";
import type { DynamicAgentDiagnostics } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";

export type AgentDiagnosticsTarget = { taskId: string; status: TaskStatus };

export type AgentDiagnosticsByTaskId = Readonly<Record<string, DynamicAgentDiagnostics>>;

// The key omits the `"git"` segment so the `diffUpdatedAt` cascade doesn't needlessly
// invalidate it, and lives under the workspace cascade so `removeWorkspaceQueriesCache`
// evicts it on close.
const agentDiagnosticsQueryKey = (
  workspaceId: string,
  taskId: string,
): readonly [string, "workspace", string, "agentDiagnostics", string] =>
  [SCULPTOR_QUERY_KEY_PREFIX, "workspace", workspaceId, "agentDiagnostics", taskId] as const;

// Freshness is driven by the status-change invalidation above, but that signal only
// fires while this hook is mounted for the workspace. A finite staleTime (instead of
// the client-wide `staleTime: Infinity`) covers the gap: if statuses changed while the
// workspace was switched away, the observers remounting on switch-back refetch data
// older than this window.
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
  const queryClient = useQueryClient();

  // Statuses each task had on the previous run of the invalidation effect. A change
  // (e.g. RUNNING→READY when a prompt completes) invalidates that task's query so the
  // now-available session is refetched; a task's first appearance is not a change (its
  // query is fetching for the first time anyway). Rebuilt from `targets` each run, so
  // removed tasks don't linger.
  const previousStatusesRef = useRef<Readonly<Record<string, TaskStatus>>>({});
  useEffect(() => {
    const previousStatuses = previousStatusesRef.current;
    const nextStatuses: Record<string, TaskStatus> = {};
    for (const { taskId, status } of targets) {
      nextStatuses[taskId] = status;
      const previousStatus = previousStatuses[taskId];
      if (previousStatus !== undefined && previousStatus !== status) {
        void queryClient.invalidateQueries({ queryKey: agentDiagnosticsQueryKey(workspaceId, taskId) });
      }
    }
    previousStatusesRef.current = nextStatuses;
  }, [targets, workspaceId, queryClient]);

  // One query per agent. `useQueries` only renders the current `targets`, so the
  // combined map can't leak entries for agents that no longer exist.
  return useQueries({
    queries: targets.map(({ taskId }) => ({
      queryKey: agentDiagnosticsQueryKey(workspaceId, taskId),
      queryFn: ({ signal }: { signal: AbortSignal }): Promise<AgentDiagnosticsQueryResult> =>
        fetchAgentDiagnostics(workspaceId, taskId, signal).then((diagnostics) => ({ taskId, diagnostics })),
      staleTime: AGENT_DIAGNOSTICS_STALE_TIME_MS,
    })),
    // A query that succeeded once keeps its last-good `data` even while a later
    // refetch is erroring, so prefer the cached diagnostics — dropping the entry
    // on a transient failure would disable the tab's copy items until the next
    // run. Only an agent that has never fetched successfully is omitted, and its
    // failure logged rather than silently presented as "no diagnostics yet".
    combine: useCallback((results: Array<{ data?: AgentDiagnosticsQueryResult; error: unknown }>) => {
      const next: Record<string, DynamicAgentDiagnostics> = {};
      for (const { data, error } of results) {
        if (data?.diagnostics !== undefined) {
          next[data.taskId] = data.diagnostics;
        } else if (error !== null) {
          console.warn("Failed to fetch workspace agent diagnostics", error);
        }
      }
      return next;
    }, []),
  });
};
