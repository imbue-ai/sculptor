import { useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useRef } from "react";

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
  const lastFailedRef = useRef<{ workspaceId: string; workspaceName: string } | null>(null);

  const execute = useCallback(
    (workspaceId: string, workspaceName: string): void => {
      const snapshot = setOptimisticDelete(workspaceId);
      if (snapshot === null) {
        return;
      }

      onNavigateAfterDelete(workspaceId);

      lastFailedRef.current = { workspaceId, workspaceName };

      posthog.capture("workspace.deleted", {
        workspace_id: workspaceId,
      });

      void deleteWorkspace({
        path: { workspace_id: workspaceId },
        meta: { skipWsAck: true },
      }).catch(() => {
        setRollbackDelete({ workspaceId, snapshot });
        setErrorToast({
          title: `Failed to delete "${workspaceName}"`,
          description: "The workspace has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: {
            label: "Retry",
            handleClick: (): void => {
              const last = lastFailedRef.current;
              if (last) {
                setErrorToast(null);
                execute(last.workspaceId, last.workspaceName);
              }
            },
          },
        });
      });
    },
    [setOptimisticDelete, setRollbackDelete, setErrorToast, onNavigateAfterDelete],
  );

  return { execute };
};
