import { useSetAtom, useStore } from "jotai";
import { posthog } from "posthog-js";
import { useCallback } from "react";

import { deleteWorkspaceAgent } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { useImbueLocation, useImbueNavigate, useImbueParams } from "../../NavigateUtils.ts";
import { optimisticDeleteTaskAtom, rollbackDeleteTaskAtom } from "../atoms/tasks";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { agentIdForWorkspaceAtomFamily, setAgentForWorkspaceAtom } from "../atoms/workspaces.ts";

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
  const store = useStore();
  const setOptimisticDelete = useSetAtom(optimisticDeleteTaskAtom);
  const setRollbackDelete = useSetAtom(rollbackDeleteTaskAtom);
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const { navigateToRoot } = useImbueNavigate();
  const { isAgentRoute } = useImbueLocation();
  const { taskID } = useImbueParams();

  const execute = useCallback(
    (taskId: string, taskTitle: string): void => {
      const snapshot = setOptimisticDelete(taskId);
      if (snapshot === null) {
        return;
      }

      // A deleted agent must not linger as the workspace's saved agent, or the next
      // cold-start redirect targets a dead route. Left cleared on a failed delete —
      // the mapping re-saves on the next agent visit.
      if (store.get(agentIdForWorkspaceAtomFamily(workspaceId)) === taskId) {
        setAgentForWorkspace({ wsId: workspaceId, agentId: null });
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
              execute(taskId, taskTitle);
            },
          },
        });
      });
    },
    [
      store,
      setOptimisticDelete,
      setRollbackDelete,
      setDeleteErrorToast,
      setAgentForWorkspace,
      onNavigateAfterDelete,
      isAgentRoute,
      taskID,
      navigateToRoot,
      workspaceId,
    ],
  );

  return { execute };
};
