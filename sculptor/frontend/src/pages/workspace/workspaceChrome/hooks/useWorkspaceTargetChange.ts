import { useMutation } from "@tanstack/react-query";
import { useSetAtom } from "jotai";

import { updateWorkspace } from "~/api";
import { ToastType, workspaceTargetChangeErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { MUTATION_SETTLE_TIMEOUT_MS } from "~/common/state/mutations/index.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";

/**
 * Change a workspace's target. Nothing is written optimistically: the stream
 * delivers the new target once the server has it, and a rejected change leaves
 * the target as it was and says so in a toast.
 */
export const useWorkspaceTargetChange = (workspaceId: string): ((targetBranch: string) => void) => {
  const setErrorToast = useSetAtom(workspaceTargetChangeErrorToastAtom);
  const { mutate } = useMutation({
    mutationFn: (targetBranch: string) =>
      updateWorkspace({
        path: { workspace_id: workspaceId },
        body: { targetBranch },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    // A mutation-level callback, so the toast still shows if the header
    // unmounts before the request fails.
    onError: (error: Error, targetBranch: string) => {
      setErrorToast({
        title: `Could not change the target to ${targetBranch}`,
        description: getErrorMessage(error, "Try again or check your connection."),
        type: ToastType.ERROR,
        action: null,
      });
    },
  });
  return mutate;
};
