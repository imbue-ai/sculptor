import { useMutation } from "@tanstack/react-query";
import { useCallback } from "react";

import { discardWorkspaceFile } from "~/api";
import { useForceRefreshWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";
import { MUTATION_SETTLE_TIMEOUT_MS } from "~/common/state/mutations/index.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";

const DISCARD_FAILED_FALLBACK = "The file's changes could not be discarded.";

type UseDiscardFileResult = {
  /** Discard `filePath`'s changes; `onDiscarded` runs once the backend has discarded them. */
  discardFile: (filePath: string, onDiscarded: () => void) => void;
  isDiscarding: boolean;
  /** Why the last discard failed; null when it succeeded or none has run since `resetError`. */
  errorMessage: string | null;
  resetError: () => void;
};

/**
 * Discard a file's changes in a workspace. Nothing is written optimistically: a
 * successful discard re-reads the diff from the backend, and a failed one leaves
 * the files as they were and says why in `errorMessage`.
 */
export const useDiscardFile = (workspaceId: string): UseDiscardFileResult => {
  const refreshDiff = useForceRefreshWorkspaceDiff(workspaceId);
  const { mutate, isPending, error, reset } = useMutation({
    mutationFn: async (filePath: string): Promise<void> => {
      const { data } = await discardWorkspaceFile({
        path: { workspace_id: workspaceId },
        body: { filePath },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      });
      if (!data.result.success) {
        throw new Error(data.result.error_message || data.result.stderr || DISCARD_FAILED_FALLBACK);
      }
    },
    // The stream delivers the recomputed diff on its own; re-reading it here only
    // takes the discarded file off the list sooner, so a failed re-read is no
    // failed discard.
    onSuccess: (): void => {
      refreshDiff().catch((refreshError: unknown) => {
        console.warn("Could not re-read the diff after a discard; the stream will deliver it.", refreshError);
      });
    },
  });

  const discardFile = useCallback(
    (filePath: string, onDiscarded: () => void): void => {
      mutate(filePath, { onSuccess: onDiscarded });
    },
    [mutate],
  );

  return {
    discardFile,
    isDiscarding: isPending,
    errorMessage: error === null ? null : getErrorMessage(error, DISCARD_FAILED_FALLBACK),
    resetError: reset,
  };
};
