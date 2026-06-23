import { type ChatMessage, ChatMessageRole } from "~/api";

export const extractUserMessageIds = (chatMessages?: Array<ChatMessage>): Array<string> => {
  if (!chatMessages) return [];

  // A Set preserves insertion order, so iterating chatMessages in order yields
  // the user message ids deduplicated and already in document order.
  const userMessageIds = new Set<string>();
  chatMessages
    .filter((message) => message.role === ChatMessageRole.USER)
    .forEach((message) => {
      userMessageIds.add(message.id);
    });

  return Array.from(userMessageIds);
};
