import { useSetAtom, useStore } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useRef } from "react";

import { ToastType } from "~/common/state/atoms/toasts.ts";

import type { CodingAgentTaskView } from "../../../api";
import { useImbueLocation, useImbueNavigate, useImbueParams } from "../../hooks/navigation.ts";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { agentIdForWorkspaceAtomFamily, setAgentForWorkspaceAtom } from "../atoms/workspaces.ts";
import { applyOptimisticTaskDelete, useDeleteTaskMutation } from "../mutations";
import { queryClient, taskQueryKey } from "../queryClient.ts";

type UseOptimisticAgentDeleteInputs = {
  workspaceId: string;
  /**
   * Custom navigation after optimistic removal. If omitted, navigates to root when the
   * deleted agent is active. Receives the deleted agent's pre-delete snapshot because the
   * optimistic removal has already dropped the agent from the store by the time this runs —
   * callbacks that need the deleted agent's data (e.g. its position among siblings) must
   * read it from the snapshot, not the store. Only invoked when the cache had the agent;
   * deleting an agent the cache never knew falls back to the default root navigation.
   */
  onNavigateAfterDelete?: (agentId: string, deletedAgent: CodingAgentTaskView) => void;
};

type UseOptimisticAgentDeleteResult = {
  execute: (agentId: string, agentTitle: string) => void;
};

export const useOptimisticAgentDelete = (inputs: UseOptimisticAgentDeleteInputs): UseOptimisticAgentDeleteResult => {
  const { workspaceId, onNavigateAfterDelete } = inputs;
  const store = useStore();
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const { navigateToRoot } = useImbueNavigate();
  const { isAgentRoute } = useImbueLocation();
  const { agentId: routedAgentId } = useImbueParams();
  const { mutateAsync: deleteTask } = useDeleteTaskMutation();
  // The Retry action re-invokes execute. Reach it through a ref (kept current
  // by the effect below) so the callback doesn't reference itself before it is
  // declared.
  const executeRef = useRef<(agentId: string, agentTitle: string) => void>(undefined);

  const execute = useCallback(
    (agentId: string, agentTitle: string): void => {
      const snapshot = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(agentId));

      // Tombstone the agent and drop it from the ids list *now*, before the
      // navigation callbacks run: the mirror projects the removal into the
      // Jotai atoms synchronously, so the callbacks below already see the agent
      // gone from every store. The mutation's onError rolls this back on
      // failure using the returned context. A missing snapshot applies
      // nothing — the DELETE is still sent (the server is the authority on
      // deletability, and a stale reference must not silently swallow the
      // user's intent).
      const deleteContext = applyOptimisticTaskDelete(agentId);

      // A deleted agent must not linger as the workspace's saved agent, or the next
      // cold-start redirect targets a dead route. Left cleared on a failed delete —
      // the mapping re-saves on the next agent visit.
      if (store.get(agentIdForWorkspaceAtomFamily(workspaceId)) === agentId) {
        setAgentForWorkspace({ wsId: workspaceId, agentId: null });
      }

      if (onNavigateAfterDelete && snapshot) {
        onNavigateAfterDelete(agentId, snapshot);
      } else if (isAgentRoute && routedAgentId === agentId) {
        navigateToRoot();
      }

      posthog.capture("agent.deleted", {
        workspace_id: workspaceId,
        agent_id: agentId,
      });

      // The mutation owns the rollback (onError, so it survives an unmount); the
      // rejection here only drives the client-state toast.
      deleteTask({ workspaceId, agentId, deleteContext }).catch(() => {
        setDeleteErrorToast({
          title: `Failed to delete "${agentTitle}"`,
          description: "The agent has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: {
            label: "Retry",
            handleClick: (): void => {
              setDeleteErrorToast(null);
              executeRef.current?.(agentId, agentTitle);
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
      routedAgentId,
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
