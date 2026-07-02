import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { ChatMessage, WorkflowTaskState } from "../../../api";
import { useWorkspacePageParams } from "../../NavigateUtils.ts";
import {
  getEmptyTaskDetailState,
  taskDetailAtomFamily,
  type TaskDetailState,
  workflowTaskStatesAtomFamily,
} from "../atoms/taskDetails";

export const useTaskDetail = (taskId: string): TaskDetailState | null => {
  return useAtomValue(taskDetailAtomFamily(taskId));
};

/**
 * Workflow-tool background task states for the task in the current URL,
 * keyed by the launching tool_use_id. Empty when no workflow has run.
 */
export const useCurrentTaskWorkflowStates = (): Record<string, WorkflowTaskState> => {
  const { agentID } = useWorkspacePageParams();
  return useAtomValue(workflowTaskStatesAtomFamily(agentID ?? ""));
};

export const useTaskDetailWithDefaults = (taskId: string): TaskDetailState => {
  const detail = useTaskDetail(taskId);
  return detail ?? getEmptyTaskDetailState();
};

export const useTaskChatMessages = (
  taskId: string,
): {
  chatMessages: Array<ChatMessage>;
  inProgressChatMessage: ChatMessage | null;
  queuedChatMessages: Array<ChatMessage>;
  workingUserMessageId: string | null;
  pendingBackgroundTaskIds: Array<string>;
} => {
  const detail = useTaskDetailWithDefaults(taskId);

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
