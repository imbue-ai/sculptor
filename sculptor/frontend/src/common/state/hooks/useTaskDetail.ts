import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { ChatMessage, WorkflowTaskState } from "../../../api";
import { useWorkspacePageParams } from "../../NavigateUtils.ts";
import {
  getEmptyTaskDetailState,
  taskDetailAtomFamily,
  type TaskDetailState,
  workflowTaskStateAtomFamily,
} from "../atoms/taskDetails";

export const useTaskDetail = (taskId: string): TaskDetailState | null => {
  return useAtomValue(taskDetailAtomFamily(taskId));
};

/**
 * The Workflow-tool background task state for one Workflow call (by its
 * launching tool_use_id) on the task in the current URL; undefined when no
 * state has arrived for it.
 */
export const useCurrentTaskWorkflowState = (toolUseId: string): WorkflowTaskState | undefined => {
  const { agentID } = useWorkspacePageParams();
  return useAtomValue(workflowTaskStateAtomFamily({ taskId: agentID ?? "", toolUseId }));
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
