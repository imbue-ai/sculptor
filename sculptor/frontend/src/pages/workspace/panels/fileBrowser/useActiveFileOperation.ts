import { useMemo } from "react";

import { useTaskChatMessages } from "~/common/state/hooks/useTaskDetail.ts";
import { isToolUseBlock } from "~/pages/workspace/utils/blockGuards.ts";
import { isDiffTool } from "~/pages/workspace/utils/toolPredicates.ts";

type ActiveFileOperation = {
  filePath: string;
  tool: string;
};

export const useActiveFileOperation = (taskId: string | undefined): ActiveFileOperation | undefined => {
  const { inProgressChatMessage } = useTaskChatMessages(taskId ?? "");

  return useMemo(() => {
    if (!taskId || !inProgressChatMessage) return undefined;

    for (const block of inProgressChatMessage.content) {
      if (!isToolUseBlock(block)) continue;

      if (!isDiffTool(block.name) && block.name !== "Delete") continue;

      const filePath = block.input?.file_path;
      if (typeof filePath !== "string" || filePath === "") continue;

      return { filePath, tool: block.name };
    }

    return undefined;
  }, [taskId, inProgressChatMessage]);
};
