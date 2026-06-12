import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect, useRef } from "react";

import { ArtifactType, getWorkspaceAgentArtifact, type GetWorkspaceAgentArtifactResponse } from "../../../api";
import { isTaskListArtifact } from "../../../common/Guards";
import {
  clearTaskUpdatedArtifactsAtom,
  taskUpdatedArtifactsAtomFamily,
  updateTaskDetailAtom,
  updateTaskUpdatedArtifactsAtom,
} from "../../../common/state/atoms/taskDetails";
import type { ArtifactsMap } from "../Types";

/**
 * Hook that watches for artifact updates in the task detail stream
 * and fetches them via HTTP.
 *
 * This is separated from the main stream processing because:
 * 1. Artifacts are large and shouldn't be fetched for background tasks
 * 2. HTTP fetching is async and separate from the WebSocket stream
 */
export const useArtifactSync = (workspaceId: string, taskId: string): void => {
  const updateTaskDetail = useSetAtom(updateTaskDetailAtom);
  const clearTaskUpdatedArtifacts = useSetAtom(clearTaskUpdatedArtifactsAtom);
  const updateTaskUpdatedArtifacts = useSetAtom(updateTaskUpdatedArtifactsAtom);
  const updatedArtifacts = useAtomValue(taskUpdatedArtifactsAtomFamily(taskId));

  // Track which artifacts are currently being fetched to avoid duplicate requests
  const inFlightArtifacts = useRef<Set<ArtifactType>>(new Set());
  // Track artifacts that received an update while a fetch was in-flight
  const needsRefetch = useRef<Set<ArtifactType>>(new Set());
  // Aborts the previous task's in-flight fetches on task switch. The refs
  // above track the CURRENT task's state, so a late response from the old
  // task must neither clear them nor re-enqueue work; checking this
  // controller's signal is how a fetch knows its bookkeeping went stale.
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchArtifact = useCallback(
    async (artifactType: ArtifactType): Promise<void> => {
      // If already fetching this artifact, mark it for re-fetch when the current fetch completes
      if (inFlightArtifacts.current.has(artifactType)) {
        needsRefetch.current.add(artifactType);
        return;
      }
      inFlightArtifacts.current.add(artifactType);
      abortControllerRef.current ??= new AbortController();
      const controller = abortControllerRef.current;

      try {
        const { data } = await getWorkspaceAgentArtifact({
          path: { workspace_id: workspaceId, agent_id: taskId, artifact_name: artifactType },
          meta: { signal: controller.signal },
        });

        if (!data) {
          console.error(`Error fetching artifact ${artifactType}: no data returned`);
          return;
        }

        const processedData = processArtifactResponse(data, artifactType);

        updateTaskDetail({
          taskId,
          updater: (currentState) => {
            if (!currentState) {
              // If no state exists, skip artifact update (shouldn't happen in practice)
              console.warn(`No task detail state found for task ${taskId}, skipping artifact update`);
              return currentState!;
            }
            return {
              ...currentState,
              artifacts: {
                ...currentState.artifacts,
                [artifactType]: processedData,
              },
            };
          },
        });
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error(`Error fetching artifact ${artifactType}:`, error);
        }
      } finally {
        // After an abort the refs belong to the NEW task — leave them alone.
        if (!controller.signal.aborted) {
          inFlightArtifacts.current.delete(artifactType);
          clearTaskUpdatedArtifacts({ taskId, artifactTypes: [artifactType] });

          // If an update arrived while we were fetching, re-enqueue via the atom
          // so the useEffect triggers a new non-recursive fetch
          if (needsRefetch.current.has(artifactType)) {
            needsRefetch.current.delete(artifactType);
            updateTaskUpdatedArtifacts({ taskId, artifactTypes: [artifactType] });
          }
        }
      }
    },
    [workspaceId, taskId, updateTaskDetail, clearTaskUpdatedArtifacts, updateTaskUpdatedArtifacts],
  );

  // Watch for updated artifacts and fetch them
  useEffect(() => {
    if (updatedArtifacts.length > 0) {
      updatedArtifacts.forEach((artifactType) => {
        fetchArtifact(artifactType);
      });
    }
  }, [updatedArtifacts, fetchArtifact]);

  // Reset requested artifacts when the viewed task changes, aborting the
  // previous task's in-flight fetches so their responses are dropped.
  useEffect(() => {
    // The Sets are stable containers for the hook's lifetime; captured here so
    // the cleanup clears the same instances it saw.
    const inFlight = inFlightArtifacts.current;
    const pendingRefetch = needsRefetch.current;
    return (): void => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      inFlight.clear();
      pendingRefetch.clear();
    };
  }, [taskId]);
};

const processArtifactResponse = (
  response: GetWorkspaceAgentArtifactResponse,
  artifactType: ArtifactType,
): ArtifactsMap[keyof ArtifactsMap] => {
  if (isTaskListArtifact(response) && artifactType === ArtifactType.PLAN) {
    return response;
  }

  throw new Error(`Artifact type mismatch: expected ${artifactType}, got ${response.objectType}`);
};
