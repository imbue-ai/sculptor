import { useMemo } from "react";

import { useAgentChatMessages } from "~/common/state/hooks/useAgentDetail.ts";
import { isToolUseBlock } from "~/pages/workspace/utils/blockGuards.ts";
import { isDiffTool } from "~/pages/workspace/utils/toolPredicates.ts";

type ActiveFileOperation = {
  filePath: string;
  tool: string;
};

export const useActiveFileOperation = (agentId: string | undefined): ActiveFileOperation | undefined => {
  const { inProgressChatMessage } = useAgentChatMessages(agentId ?? "");

  return useMemo(() => {
    if (!agentId || !inProgressChatMessage) return undefined;

    for (const block of inProgressChatMessage.content) {
      if (!isToolUseBlock(block)) continue;

      if (!isDiffTool(block.name) && block.name !== "Delete") continue;

      const filePath = block.input?.file_path;
      if (typeof filePath !== "string" || filePath === "") continue;

      return { filePath, tool: block.name };
    }

    return undefined;
  }, [agentId, inProgressChatMessage]);
};
