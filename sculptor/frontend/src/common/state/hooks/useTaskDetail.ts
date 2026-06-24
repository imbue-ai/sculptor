import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { ChatMessage } from "../../../api";
import { getEmptyTaskDetailState, taskDetailAtomFamily, type TaskDetailState } from "../atoms/taskDetails";

export const useTaskDetail = (taskId: string): TaskDetailState | null => {
  return useAtomValue(taskDetailAtomFamily(taskId));
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
