import { useMutation } from "@tanstack/react-query";
import { useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useEffect, useRef } from "react";

import { removeWorkspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { removeWorkspaceAgentActionState } from "~/pages/workspace/panels/workspaceAgentActions.ts";

import { deleteWorkspace } from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { HTTPException } from "../../Errors.ts";
import { queryClient, recentWorkspacesQueryKey } from "../../queryClient.ts";
import { workspaceDeleteErrorToastAtom } from "../atoms/toasts";
import type { WorkspaceDeleteContext } from "../atoms/workspaces";
import {
  finalizeDeleteWorkspaceAtom,
  optimisticDeleteWorkspaceAtom,
  rollbackDeleteWorkspaceAtom,
} from "../atoms/workspaces";
import { MUTATION_SETTLE_TIMEOUT_MS } from "../mutations";

type UseOptimisticWorkspaceDeleteInputs = {
  onNavigateAfterDelete: (workspaceId: string) => void;
};

type UseOptimisticWorkspaceDeleteResult = {
  execute: (workspaceId: string, workspaceName: string) => void;
};

type DeleteWorkspaceVars = {
  workspaceId: string;
  context: WorkspaceDeleteContext;
};

export const useOptimisticWorkspaceDelete = (
  inputs: UseOptimisticWorkspaceDeleteInputs,
): UseOptimisticWorkspaceDeleteResult => {
  const { onNavigateAfterDelete } = inputs;
  const setOptimisticDelete = useSetAtom(optimisticDeleteWorkspaceAtom);
  const setRollbackDelete = useSetAtom(rollbackDeleteWorkspaceAtom);
  const setFinalizeDelete = useSetAtom(finalizeDeleteWorkspaceAtom);
  const setErrorToast = useSetAtom(workspaceDeleteErrorToastAtom);
  const removeWorkspaceLayout = useSetAtom(removeWorkspaceLayoutAtom);
  // The Retry action re-invokes execute. Reach it through a ref (kept current
  // by the effect below) so the callback doesn't reference itself before it is
  // declared.
  const executeRef = useRef<(workspaceId: string, workspaceName: string) => void>(undefined);

  const { mutateAsync: runDelete } = useMutation({
    mutationFn: async ({ workspaceId }: DeleteWorkspaceVars): Promise<void> => {
      try {
        await deleteWorkspace({
          path: { workspace_id: workspaceId },
          meta: { skipWsAck: true, timeout: MUTATION_SETTLE_TIMEOUT_MS },
        });
      } catch (error) {
        // An already-deleted workspace is a success for the user's intent —
        // let the tombstone stand instead of "restoring" something the
        // server no longer has.
        if (error instanceof HTTPException && error.status === 404) {
          return;
        }
        throw error;
      }
    },
    // Rollback lives at the mutation level (not the caller's .catch) so an
    // unmount mid-request cannot skip it. The rollback atom yields to any
    // authoritative frame that landed while the request was in flight.
    onError: (_error, vars): void => {
      setRollbackDelete({ workspaceId: vars.workspaceId, context: vars.context });
    },
    onSuccess: (_data, vars): void => {
      // Success-only cleanup: drop the workspace's caches, setup status, and
      // open/close intent. Deferred to here (not apply time) so a failed
      // delete restores the UI exactly as it was; the layout is re-seeded to
      // default on next visit.
      setFinalizeDelete(vars.workspaceId);
      removeWorkspaceLayout({ workspaceId: vars.workspaceId });
      removeWorkspaceAgentActionState(vars.workspaceId);
      // The Home recent list is pulled, not pushed — refresh it so a
      // confirmed delete disappears even when the stream is down.
      void queryClient.invalidateQueries({ queryKey: recentWorkspacesQueryKey() });
    },
  });

  const execute = useCallback(
    (workspaceId: string, workspaceName: string): void => {
      // Apply the local tombstone when the store knows the workspace. Either
      // way the DELETE goes to the server: the store's ignorance (e.g. a Home
      // row the stream never delivered) must not silently swallow the user's
      // intent — the server is the authority on deletability.
      const context = setOptimisticDelete(workspaceId);

      onNavigateAfterDelete(workspaceId);

      posthog.capture("workspace.deleted", {
        workspace_id: workspaceId,
      });

      // The mutation owns rollback and success cleanup (its onError/onSuccess
      // survive an unmount); the rejection here only drives the toast.
      runDelete({ workspaceId, context }).catch(() => {
        setErrorToast({
          title: `Failed to delete "${workspaceName}"`,
          description:
            context.snapshot === null
              ? "Try again or check your connection."
              : "The workspace has been restored. Try again or check your connection.",
          type: ToastType.ERROR_PROMINENT,
          action: {
            label: "Retry",
            handleClick: (): void => {
              setErrorToast(null);
              executeRef.current?.(workspaceId, workspaceName);
            },
          },
        });
      });
    },
    [setOptimisticDelete, setErrorToast, onNavigateAfterDelete, runDelete],
  );

  useEffect(() => {
    executeRef.current = execute;
  }, [execute]);

  return { execute };
};
