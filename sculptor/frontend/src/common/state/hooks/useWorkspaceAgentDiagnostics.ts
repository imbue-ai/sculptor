// Fetches per-agent diagnostics (claude session id + claude/Sculptor transcript file
// paths) for the active workspace's agents, powering the panel-tab context-menu copy
// actions (AGENT-06). The copy items are derived from this data in dynamicPanels, so
// the session/transcript items stay disabled until a session exists and become enabled
// once the agent has run.
//
// Each agent is fetched once per (id, status) pair: an agent with no session yet
// returns empty diagnostics, and the refetch when its status changes (e.g. after the
// first prompt completes) picks up the now-available session. The result is a stable
// map keyed by task id, so the registry-sync hook can read agent.diagnostics without
// triggering a fetch on every task tick.

import { useEffect, useRef, useState } from "react";

import type { TaskStatus } from "~/api";
import { getWorkspaceAgentDiagnostics } from "~/api";
import type { DynamicAgentDiagnostics } from "~/components/sections/registry/dynamicPanels.tsx";

export type AgentDiagnosticsTarget = { taskId: string; status: TaskStatus };

export type AgentDiagnosticsByTaskId = Readonly<Record<string, DynamicAgentDiagnostics>>;

export const useWorkspaceAgentDiagnostics = (
  workspaceId: string,
  targets: ReadonlyArray<AgentDiagnosticsTarget>,
): AgentDiagnosticsByTaskId => {
  const [diagnosticsByTaskId, setDiagnosticsByTaskId] = useState<AgentDiagnosticsByTaskId>({});
  // The (taskId → last-fetched-status) we have a result for, so we refetch only when an
  // agent appears or its status changes (not on every unrelated task tick).
  const fetchedStatusByTaskId = useRef<Map<string, TaskStatus>>(new Map());

  useEffect(() => {
    let isCancelled = false;
    const liveTaskIds = new Set(targets.map((target) => target.taskId));

    // Drop diagnostics for agents that no longer exist so the map can't leak.
    fetchedStatusByTaskId.current.forEach((_status, taskId) => {
      if (!liveTaskIds.has(taskId)) {
        fetchedStatusByTaskId.current.delete(taskId);
      }
    });

    for (const { taskId, status } of targets) {
      if (fetchedStatusByTaskId.current.get(taskId) === status) {
        continue;
      }
      fetchedStatusByTaskId.current.set(taskId, status);
      void getWorkspaceAgentDiagnostics({
        path: { workspace_id: workspaceId, agent_id: taskId },
        throwOnError: false,
      }).then(({ data }) => {
        if (isCancelled || data === undefined) {
          return;
        }
        setDiagnosticsByTaskId((prev) => ({
          ...prev,
          [taskId]: {
            sessionId: data.sessionId ?? null,
            claudeTranscriptPath: data.transcriptFilePath ?? null,
            sculptorTranscriptPath: data.sculptorTranscriptFilePath ?? null,
          },
        }));
      });
    }

    // Evict stale map entries (outside the fetch loop so a status change replaces
    // rather than removes the entry).
    setDiagnosticsByTaskId((prev) => {
      const next: Record<string, DynamicAgentDiagnostics> = {};
      let didChange = false;
      for (const taskId of Object.keys(prev)) {
        if (liveTaskIds.has(taskId)) {
          next[taskId] = prev[taskId];
        } else {
          didChange = true;
        }
      }
      return didChange ? next : prev;
    });

    return (): void => {
      isCancelled = true;
    };
  }, [workspaceId, targets]);

  return diagnosticsByTaskId;
};
