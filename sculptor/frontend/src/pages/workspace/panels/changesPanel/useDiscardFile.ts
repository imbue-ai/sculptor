import { useCallback, useState } from "react";

import { discardWorkspaceFile } from "~/api";
import { useForceRefreshWorkspaceDiff } from "~/common/state/hooks/useWorkspaceDiff.ts";

type UseDiscardFileResult = {
  discardFile: (filePath: string) => Promise<boolean>;
  isDiscarding: boolean;
};

export const useDiscardFile = (workspaceId: string): UseDiscardFileResult => {
  const [isDiscarding, setIsDiscarding] = useState<boolean>(false);
  const refreshDiff = useForceRefreshWorkspaceDiff(workspaceId);

  const discardFile = useCallback(
    async (filePath: string): Promise<boolean> => {
      setIsDiscarding(true);
      try {
        const { data } = await discardWorkspaceFile({
          path: { workspace_id: workspaceId },
          body: { filePath },
        });

        if (data?.result?.success) {
          await refreshDiff();
          return true;
        }
        return false;
      } catch (error: unknown) {
        console.error("Error discarding file:", error);
        return false;
      } finally {
        setIsDiscarding(false);
      }
    },
    [workspaceId, refreshDiff],
  );

  return { discardFile, isDiscarding };
};
