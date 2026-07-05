import { useSetAtom, useStore } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useRef } from "react";

import { ToastType } from "~/common/state/atoms/toasts.ts";

import type { CodingAgentTaskView } from "../../../api";
import { deleteWorkspaceAgent } from "../../../api";
import { useImbueLocation, useImbueNavigate, useImbueParams } from "../../hooks/navigation.ts";
import { optimisticDeleteAgentAtom, rollbackDeleteAgentAtom } from "../atoms/agents";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { agentIdForWorkspaceAtomFamily, setAgentForWorkspaceAtom } from "../atoms/workspaces.ts";

type UseOptimisticAgentDeleteInputs = {
  workspaceId: string;
  /**
   * Custom navigation after optimistic removal. If omitted, navigates to root when the
   * deleted agent is active. Receives the deleted agent's pre-delete snapshot because the
   * optimistic removal has already dropped the agent from the store by the time this runs —
   * callbacks that need the deleted agent's data (e.g. its position among siblings) must
   * read it from the snapshot, not the store.
   */
  onNavigateAfterDelete?: (agentId: string, deletedAgent: CodingAgentTaskView) => void;
};

type UseOptimisticAgentDeleteResult = {
  execute: (agentId: string, agentTitle: string) => void;
};

export const useOptimisticAgentDelete = (inputs: UseOptimisticAgentDeleteInputs): UseOptimisticAgentDeleteResult => {
  const { workspaceId, onNavigateAfterDelete } = inputs;
  const store = useStore();
  const setOptimisticDelete = useSetAtom(optimisticDeleteAgentAtom);
  const setRollbackDelete = useSetAtom(rollbackDeleteAgentAtom);
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);
  const setAgentForWorkspace = useSetAtom(setAgentForWorkspaceAtom);
  const { navigateToRoot } = useImbueNavigate();
  const { isAgentRoute } = useImbueLocation();
  const { agentId: routedAgentId } = useImbueParams();
  // The Retry action re-invokes execute. Reach it through a ref (kept current
  // by the effect below) so the callback doesn't reference itself before it is
  // declared.
  const executeRef = useRef<(agentId: string, agentTitle: string) => void>(undefined);

  const execute = useCallback(
    (agentId: string, agentTitle: string): void => {
      const snapshot = setOptimisticDelete(agentId);
      if (snapshot === null) {
        return;
      }

      // A deleted agent must not linger as the workspace's saved agent, or the next
      // cold-start redirect targets a dead route. Left cleared on a failed delete —
      // the mapping re-saves on the next agent visit.
      if (store.get(agentIdForWorkspaceAtomFamily(workspaceId)) === agentId) {
        setAgentForWorkspace({ wsId: workspaceId, agentId: null });
      }

      if (onNavigateAfterDelete) {
        onNavigateAfterDelete(agentId, snapshot);
      } else if (isAgentRoute && routedAgentId === agentId) {
        navigateToRoot();
      }

      posthog.capture("agent.deleted", {
        workspace_id: workspaceId,
        agent_id: agentId,
      });

      void deleteWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: agentId },
        meta: { skipWsAck: true },
      }).catch(() => {
        setRollbackDelete({ agentId, snapshot });
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
      setOptimisticDelete,
      setRollbackDelete,
      setDeleteErrorToast,
      setAgentForWorkspace,
      onNavigateAfterDelete,
      isAgentRoute,
      routedAgentId,
      navigateToRoot,
      workspaceId,
    ],
  );

  useEffect(() => {
    executeRef.current = execute;
  }, [execute]);

  return { execute };
};
