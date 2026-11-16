import { useMutation } from "@tanstack/react-query";

import { updateStaleWorkingCopy } from "~/api";
import { MUTATION_SETTLE_TIMEOUT_MS } from "~/common/state/mutations/index.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";

type UseUpdateStaleWorkingCopyResult = {
  updateWorkingCopy: () => void;
  isUpdating: boolean;
  /** Why the last update failed; null when it succeeded or none has run. */
  errorMessage: string | null;
};

/**
 * Bring a jj workspace's stale working copy up to date, on the user's request.
 * Nothing is written optimistically: the stream reports the working copy as
 * current once the backend has updated it, and a failed update leaves it stale
 * and says why in `errorMessage`.
 */
export const useUpdateStaleWorkingCopy = (workspaceId: string): UseUpdateStaleWorkingCopyResult => {
  const { mutate, isPending, error } = useMutation({
    mutationFn: () =>
      updateStaleWorkingCopy({
        path: { workspace_id: workspaceId },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
  });
  return {
    updateWorkingCopy: () => mutate(),
    isUpdating: isPending,
    errorMessage: error === null ? null : getErrorMessage(error, "Try again or check your connection."),
  };
};
