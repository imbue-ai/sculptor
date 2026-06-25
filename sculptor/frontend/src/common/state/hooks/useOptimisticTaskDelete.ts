import { useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useRef } from "react";

import { deleteWorkspaceAgent } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { useImbueLocation, useImbueNavigate, useImbueParams } from "../../NavigateUtils.ts";
import { optimisticDeleteTaskAtom, rollbackDeleteTaskAtom } from "../atoms/tasks";
import { deleteErrorToastAtom } from "../atoms/toasts";

type UseOptimisticTaskDeleteInputs = {
  workspaceId: string;
  /** Custom navigation after optimistic removal. If omitted, navigates to root when the deleted agent is active. */
  onNavigateAfterDelete?: (taskId: string) => void;
};

type UseOptimisticTaskDeleteResult = {
  execute: (taskId: string, taskTitle: string) => void;
};

export const useOptimisticTaskDelete = (inputs: UseOptimisticTaskDeleteInputs): UseOptimisticTaskDeleteResult => {
  const { workspaceId, onNavigateAfterDelete } = inputs;
  const setOptimisticDelete = useSetAtom(optimisticDeleteTaskAtom);
  const setRollbackDelete = useSetAtom(rollbackDeleteTaskAtom);
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);
  const { navigateToRoot } = useImbueNavigate();
  const { isAgentRoute } = useImbueLocation();
  const { taskID } = useImbueParams();
  // The Retry action re-invokes execute. Reach it through a ref (kept current
  // by the effect below) so the callback doesn't reference itself before it is
  // declared.
  const executeRef = useRef<(taskId: string, taskTitle: string) => void>(undefined);

  const execute = useCallback(
    (taskId: string, taskTitle: string): void => {
      const snapshot = setOptimisticDelete(taskId);
      if (snapshot === null) {
        return;
      }

      if (onNavigateAfterDelete) {
        onNavigateAfterDelete(taskId);
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
        setRollbackDelete({ taskId, snapshot });
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
      setOptimisticDelete,
      setRollbackDelete,
      setDeleteErrorToast,
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
