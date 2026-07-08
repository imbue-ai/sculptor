import { useSetAtom, useStore } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useRef } from "react";

import type { CodingAgentTaskView } from "../../../api";
import { deleteWorkspaceAgent } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { useImbueLocation, useImbueNavigate, useImbueParams } from "../../NavigateUtils.ts";
import { getTaskSyncVersion, queryClient, taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { agentIdForWorkspaceAtomFamily, setAgentForWorkspaceAtom } from "../atoms/workspaces.ts";

type UseOptimisticTaskDeleteInputs = {
  workspaceId: string;
  /**
   * Custom navigation after optimistic removal. If omitted, navigates to root when the
   * deleted agent is active. Receives the deleted task's pre-delete snapshot because the
   * optimistic removal has already dropped the task from the store by the time this runs —
   * callbacks that need the deleted task's data (e.g. its position among siblings) must
   * read it from the snapshot, not the store.
   */
  onNavigateAfterDelete?: (taskId: string, deletedTask: CodingAgentTaskView) => void;
};

type UseOptimisticTaskDeleteResult = {
  execute: (taskId: string, taskTitle: string) => void;
};

export const useOptimisticTaskDelete = (inputs: UseOptimisticTaskDeleteInputs): UseOptimisticTaskDeleteResult => {
  const { workspaceId, onNavigateAfterDelete } = inputs;
  const store = useStore();
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const { navigateToRoot } = useImbueNavigate();
  const { isAgentRoute } = useImbueLocation();
  const { taskID } = useImbueParams();
  // The Retry action re-invokes execute. Reach it through a ref (kept current
  // by the effect below) so the callback doesn't reference itself before it is
  // declared.
  const executeRef = useRef<(taskId: string, taskTitle: string) => void>(undefined);

  const execute = useCallback(
    (taskId: string, taskTitle: string): void => {
      const snapshot = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(taskId));
      if (!snapshot) {
        return;
      }
      const syncVersion = getTaskSyncVersion(taskId);

      // Tombstone the task and drop it from the ids list. The mirror projects
      // the removal into the Jotai atoms synchronously, so the navigation
      // callbacks below already see the task gone from every store.
      queryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey(taskId), null);
      const currentIds = queryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey()) ?? [];
      queryClient.setQueryData<ReadonlyArray<string>>(
        taskIdsQueryKey(),
        currentIds.filter((id) => id !== taskId),
      );

      // A deleted agent must not linger as the workspace's saved agent, or the next
      // cold-start redirect targets a dead route. Left cleared on a failed delete —
      // the mapping re-saves on the next agent visit.
      if (store.get(agentIdForWorkspaceAtomFamily(workspaceId)) === taskId) {
        setAgentForWorkspace({ wsId: workspaceId, agentId: null });
      }

      if (onNavigateAfterDelete) {
        onNavigateAfterDelete(taskId, snapshot);
      } else if (isAgentRoute && taskID === taskId) {
        navigateToRoot();
      }

      posthog.capture("agent.deleted", {
        workspace_id: workspaceId,
        agent_id: taskId,
      });

      void deleteWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: taskId },
        meta: { skipWsAck: true },
      }).catch(() => {
        // Restore the snapshot unless a WS frame wrote the task while the
        // request was in flight — the frame holds server truth and must win.
        if (getTaskSyncVersion(taskId) === syncVersion) {
          queryClient.setQueryData(taskQueryKey(taskId), snapshot);
          const restoredIds = queryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey()) ?? [];
          if (!restoredIds.includes(taskId)) {
            queryClient.setQueryData(taskIdsQueryKey(), [...restoredIds, taskId]);
          }
        }
        setDeleteErrorToast({
          title: `Failed to delete "${taskTitle}"`,
          description: "The agent has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: {
            label: "Retry",
            handleClick: (): void => {
              setDeleteErrorToast(null);
              executeRef.current?.(taskId, taskTitle);
            },
          },
        });
      });
    },
    [
      store,
      setDeleteErrorToast,
      setAgentForWorkspace,
      onNavigateAfterDelete,
      isAgentRoute,
      taskID,
      navigateToRoot,
      workspaceId,
    ],
  );

  useEffect(() => {
    executeRef.current = execute;
  }, [execute]);

  return { execute };
};
