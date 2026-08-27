import type {
  AskUserQuestionData,
  ChatMessage,
  SubmittedQuestionAnswers,
  TaskUpdate,
  WorkflowTaskState,
} from "../../api";

type ChatMessagesState = {
  completedChatMessages: Array<ChatMessage>;
  inProgressChatMessage: ChatMessage | null;
  queuedChatMessages: Array<ChatMessage>;
  workingUserMessageId: string | null;
  pendingUserQuestion: AskUserQuestionData | null;
  submittedQuestionAnswers: Record<string, SubmittedQuestionAnswers>;
  isInPlanMode: boolean;
  pendingBackgroundTaskIds: Array<string>;
  workflowTaskStates: Record<string, WorkflowTaskState>;
};

export const chatMessagesReducer = (currentState: ChatMessagesState, taskUpdate: TaskUpdate): ChatMessagesState => {
  const newChatMessages = taskUpdate.chatMessages ?? [];

  const updatedCompletedMessages = mergeAndDeduplicateMessages(currentState.completedChatMessages, newChatMessages);

  return {
    completedChatMessages: updatedCompletedMessages,
    inProgressChatMessage: taskUpdate.inProgressChatMessage,
    queuedChatMessages: taskUpdate.queuedChatMessages,
    workingUserMessageId: taskUpdate.inProgressUserMessageId,
    pendingUserQuestion:
      taskUpdate.pendingUserQuestion !== undefined
        ? taskUpdate.pendingUserQuestion
        : (currentState.pendingUserQuestion ?? null),
    submittedQuestionAnswers:
      taskUpdate.submittedQuestionAnswers !== undefined
        ? { ...currentState.submittedQuestionAnswers, ...taskUpdate.submittedQuestionAnswers }
        : currentState.submittedQuestionAnswers,
    isInPlanMode:
      taskUpdate.isInPlanMode !== undefined ? taskUpdate.isInPlanMode : (currentState.isInPlanMode ?? false),
    // Backend ships a full snapshot of pending background task IDs on every
    // update — the count only changes on Started / Notification messages,
    // so replacing (rather than merging) keeps the wait-state signal in
    // sync with the harness's actual state. See SCU-387.
    pendingBackgroundTaskIds:
      taskUpdate.pendingBackgroundTaskIds !== undefined
        ? taskUpdate.pendingBackgroundTaskIds
        : (currentState.pendingBackgroundTaskIds ?? []),
    // A map (possibly empty) is a full snapshot — replace, don't merge.
    // null/undefined means unchanged: the backend suppresses the map from
    // updates where no workflow state changed, since it can grow large.
    workflowTaskStates: taskUpdate.workflowTaskStates ?? currentState.workflowTaskStates ?? {},
  };
};

const mergeAndDeduplicateMessages = (
  currentMessages: Array<ChatMessage>,
  newMessages: Array<ChatMessage>,
): Array<ChatMessage> => {
  if (newMessages.length === 0) {
    return currentMessages;
  }

  const messageById = Object.fromEntries(currentMessages.map((msg) => [msg.id, { ...msg }]));
  for (const msg of newMessages) {
    messageById[msg.id] = { ...msg };
  }

  // Collapse IDs that appear in both the current and incoming lists to a
  // single entry while preserving first-seen insertion order.
  const allUniqueMessageIds: Array<string> = [];
  for (const msg of [...currentMessages, ...newMessages]) {
    if (!allUniqueMessageIds.includes(msg.id)) {
      allUniqueMessageIds.push(msg.id);
    }
  }

  return allUniqueMessageIds.map((id) => messageById[id]);
};
