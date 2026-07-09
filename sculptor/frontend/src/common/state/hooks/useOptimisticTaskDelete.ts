import { useSetAtom, useStore } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useRef } from "react";

import type { CodingAgentTaskView } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { useImbueLocation, useImbueNavigate, useImbueParams } from "../../NavigateUtils.ts";
import { queryClient, taskQueryKey } from "../../queryClient.ts";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { agentIdForWorkspaceAtomFamily, setAgentForWorkspaceAtom } from "../atoms/workspaces.ts";
import { applyOptimisticTaskDelete, useDeleteTaskMutation } from "../mutations";

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
  const { mutateAsync: deleteTask } = useDeleteTaskMutation();
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

      // Tombstone the task and drop it from the ids list *now*, before the
      // navigation callbacks run: the mirror projects the removal into the
      // Jotai atoms synchronously, so the callbacks below already see the task
      // gone from every store. The mutation's onError rolls this back on
      // failure using the returned context.
      const deleteContext = applyOptimisticTaskDelete(taskId);

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

      // The mutation owns the rollback (onError, so it survives an unmount); the
      // rejection here only drives the client-state toast.
      deleteTask({ workspaceId, agentId: taskId, deleteContext }).catch(() => {
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
      deleteTask,
    ],
    // deleteTask (mutateAsync) is referentially stable across renders.
  );

  useEffect(() => {
    executeRef.current = execute;
  }, [execute]);

  return { execute };
};
