import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { ChatMessage, WorkflowTaskState } from "../../../api";
import { useWorkspacePageParams } from "../../hooks/navigation.ts";
import {
  type AgentDetailState,
  agentDetailStateAtomFamily,
  getEmptyAgentDetailState,
  workflowTaskStateAtomFamily,
} from "../atoms/agentDetails";

export const useAgentDetail = (agentId: string): AgentDetailState | null => {
  return useAtomValue(agentDetailStateAtomFamily(agentId));
};

/**
 * The Workflow-tool background task state for one Workflow call (by its
 * launching tool_use_id) on the agent in the current URL; undefined when no
 * state has arrived for it.
 */
export const useCurrentAgentWorkflowState = (toolUseId: string): WorkflowTaskState | undefined => {
  const { agentID } = useWorkspacePageParams();
  return useAtomValue(workflowTaskStateAtomFamily({ agentId: agentID ?? "", toolUseId }));
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
