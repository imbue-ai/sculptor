import type { ChatMessage } from "../../../api";
import { ChatMessageRole } from "../../../api";

export const extractUserMessageIds = (chatMessages?: Array<ChatMessage>): Array<string> => {
  if (!chatMessages) return [];

  const userMessageIds = new Set<string>();
  chatMessages
    .filter((message) => message.role === ChatMessageRole.USER)
    .forEach((message) => {
      userMessageIds.add(message.id);
    });

  const sortedUserMessageIds = Array.from(userMessageIds).sort((a, b) => {
    const indexA = chatMessages.findIndex((msg) => msg.id === a);
    const indexB = chatMessages.findIndex((msg) => msg.id === b);
    return indexA - indexB;
  });

  return sortedUserMessageIds;
};
