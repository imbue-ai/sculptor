import { useMemo } from "react";

import { isToolUseBlock } from "~/common/Guards.ts";
import { useTaskChatMessages } from "~/common/state/hooks/useTaskDetail.ts";
import { isDiffTool } from "~/pages/workspace/utils/utils.ts";

type ActiveFileOperation = {
  filePath: string;
  tool: string;
};

export const useActiveFileOperation = (taskId: string | undefined): ActiveFileOperation | null => {
  const { inProgressChatMessage } = useTaskChatMessages(taskId ?? "");

  return useMemo(() => {
    if (!taskId || !inProgressChatMessage) return null;

    for (const block of inProgressChatMessage.content) {
      if (!isToolUseBlock(block)) continue;

      if (!isDiffTool(block.name) && block.name !== "Delete") continue;

      const filePath = block.input?.file_path;
      if (typeof filePath !== "string" || filePath === "") continue;

      return { filePath, tool: block.name };
    }

    return null;
  }, [taskId, inProgressChatMessage]);
};
