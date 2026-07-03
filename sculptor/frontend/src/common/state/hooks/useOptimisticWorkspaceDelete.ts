import { useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback } from "react";

import { removeWorkspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { removeWorkspaceAgentActionState } from "~/pages/workspace/panels/workspaceAgentActions.ts";

import { deleteWorkspace } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { workspaceDeleteErrorToastAtom } from "../atoms/toasts";
import { optimisticDeleteWorkspaceAtom, rollbackDeleteWorkspaceAtom } from "../atoms/workspaces";

type UseOptimisticWorkspaceDeleteInputs = {
  onNavigateAfterDelete: (workspaceId: string) => void;
};

type UseOptimisticWorkspaceDeleteResult = {
  execute: (workspaceId: string, workspaceName: string) => void;
};

export const useOptimisticWorkspaceDelete = (
  inputs: UseOptimisticWorkspaceDeleteInputs,
): UseOptimisticWorkspaceDeleteResult => {
  const { onNavigateAfterDelete } = inputs;
  const setOptimisticDelete = useSetAtom(optimisticDeleteWorkspaceAtom);
  const setRollbackDelete = useSetAtom(rollbackDeleteWorkspaceAtom);
  const setErrorToast = useSetAtom(workspaceDeleteErrorToastAtom);
  const removeWorkspaceLayout = useSetAtom(removeWorkspaceLayoutAtom);

  const execute = useCallback(
    (workspaceId: string, workspaceName: string): void => {
      const snapshot = setOptimisticDelete(workspaceId);
      if (snapshot === null) {
        return;
      }

      onNavigateAfterDelete(workspaceId);

      posthog.capture("workspace.deleted", {
        workspace_id: workspaceId,
      });

      void deleteWorkspace({
        path: { workspace_id: workspaceId },
        meta: { skipWsAck: true },
      })
        .then(() => {
          // Drop the workspace's persisted layout only once the server delete commits,
          // so a failed delete (rolled back below) keeps the user's arrangement;
          // the layout is re-seeded to default on next visit.
          removeWorkspaceLayout({ workspaceId });
          // Free the workspace-keyed agent-resolution/action atoms alongside the layout.
          removeWorkspaceAgentActionState(workspaceId);
        })
        .catch(() => {
          setRollbackDelete({ workspaceId, snapshot });
          setErrorToast({
            title: `Failed to delete "${workspaceName}"`,
            description: "The workspace has been restored. Try again or check your connection.",
            type: ToastType.ERROR_PROMINENT,
            action: {
              label: "Retry",
              handleClick: (): void => {
                setErrorToast(null);
                execute(workspaceId, workspaceName);
              },
            },
          });
        });
    },
    [setOptimisticDelete, setRollbackDelete, setErrorToast, onNavigateAfterDelete, removeWorkspaceLayout],
  );

  return { execute };
};
