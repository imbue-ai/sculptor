import { useAtomValue, useSetAtom } from "jotai";
import { useEffect } from "react";

import { ArtifactType, type CodingAgentTaskView, getWorkspaceAgentArtifact } from "~/api";
import { isTaskListArtifact } from "~/common/Guards.ts";
import {
  getEmptyTaskDetailState,
  taskDetailAtomFamily,
  updateTaskDetailAtom,
} from "~/common/state/atoms/taskDetails.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useTask } from "~/common/state/hooks/useTaskHelpers.ts";
import type { ArtifactsMap } from "~/pages/workspace/Types.ts";

import { useWorkspacePluginContext } from "../WorkspaceContext.tsx";

/** Current workspace id, read from the host-provided plugin context. */
export const useWorkspaceId = (): string => useWorkspacePluginContext().workspaceId;

/**
 * All non-deleted tasks for the workspace the plugin is mounted in. Returns
 * `undefined` until the host's task stream has produced its first batch.
 */
export const useWorkspaceTasks = (): ReadonlyArray<CodingAgentTaskView> | undefined => {
  const { workspaceId } = useWorkspacePluginContext();
  const tasks = useAtomValue(tasksArrayAtom);
  if (tasks === undefined) return undefined;
  return tasks.filter((t) => t.workspaceId === workspaceId);
};

/**
 * Returns the named artifact for a task, fetching it on demand and caching the
 * result in the host's task-detail atom so multiple consumers share one fetch.
 *
 * In the prototype this is a hand-rolled fetch-on-mount; later it will move
 * to TanStack Query keyed by [`artifact`, taskId, type] and the public hook
 * signature won't change.
 */
export const useTaskArtifact = <T extends keyof ArtifactsMap>(
  taskId: string,
  artifactType: T,
): ArtifactsMap[T] | undefined => {
  const task = useTask(taskId);
  const detail = useAtomValue(taskDetailAtomFamily(taskId));
  const updateTaskDetail = useSetAtom(updateTaskDetailAtom);

  const workspaceId = task?.workspaceId ?? null;
  const cached = detail?.artifacts[artifactType];

  useEffect(() => {
    if (!workspaceId || cached !== undefined) return;
    let isCancelled = false;

    void (async (): Promise<void> => {
      try {
        const { data } = await getWorkspaceAgentArtifact({
          path: {
            workspace_id: workspaceId,
            agent_id: taskId,
            artifact_name: artifactType,
          },
        });
        if (isCancelled || !data) return;
        const processed = processArtifactResponse(data, artifactType);
        if (processed === null) return;

        updateTaskDetail({
          taskId,
          updater: (prev) => {
            const base = prev ?? getEmptyTaskDetailState();
            return {
              ...base,
              artifacts: { ...base.artifacts, [artifactType]: processed },
            };
          },
        });
      } catch (e) {
        // Swallow — surfacing fetch errors is host UX, not the plugin's job
        // to discover. The plugin sees `undefined` and renders its own
        // empty state.
        console.error("useTaskArtifact fetch failed", { taskId, artifactType }, e);
      }
    })();

    return (): void => {
      isCancelled = true;
    };
  }, [workspaceId, taskId, artifactType, cached, updateTaskDetail]);

  return cached as ArtifactsMap[T] | undefined;
};

const processArtifactResponse = <T extends keyof ArtifactsMap>(
  response: Awaited<ReturnType<typeof getWorkspaceAgentArtifact>>["data"],
  artifactType: T,
): ArtifactsMap[T] | null => {
  if (!response) return null;
  if (artifactType === ArtifactType.PLAN && isTaskListArtifact(response)) {
    return response as ArtifactsMap[T];
  }
  // TODO(plugins): the USAGE branch was dropped when the host removed the
  // USAGE artifact. Re-add a case here once the cost/token data has a new
  // artifact (see workspace-cost-tracker plugin).
  return null;
};
