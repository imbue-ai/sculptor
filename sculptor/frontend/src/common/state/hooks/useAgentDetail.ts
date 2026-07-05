import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { ChatMessage } from "../../../api";
import { type AgentDetailState, agentDetailStateAtomFamily, getEmptyAgentDetailState } from "../atoms/agentDetails";

export const useAgentDetail = (agentId: string): AgentDetailState | null => {
  return useAtomValue(agentDetailStateAtomFamily(agentId));
};

export const useAgentDetailWithDefaults = (agentId: string): AgentDetailState => {
  const detail = useAgentDetail(agentId);
  return detail ?? getEmptyAgentDetailState();
};

export const useAgentChatMessages = (
  agentId: string,
): {
  chatMessages: Array<ChatMessage>;
  inProgressChatMessage: ChatMessage | null;
  queuedChatMessages: Array<ChatMessage>;
  workingUserMessageId: string | null;
  pendingBackgroundTaskIds: Array<string>;
} => {
  const detail = useAgentDetailWithDefaults(agentId);

  const chatMessages = useMemo(() => {
    if (detail.inProgressChatMessage) {
      return [...detail.completedChatMessages, detail.inProgressChatMessage];
    }
    return detail.completedChatMessages;
  }, [detail.completedChatMessages, detail.inProgressChatMessage]);

  return {
    chatMessages,
    inProgressChatMessage: detail.inProgressChatMessage,
    queuedChatMessages: detail.queuedChatMessages,
    workingUserMessageId: detail.workingUserMessageId,
    pendingBackgroundTaskIds: detail.pendingBackgroundTaskIds,
  };
};
