import type { ChatMessage, ToolResultBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import type { BlockUnion } from "~/common/Guards";
import { isToolResultBlock } from "~/common/Guards";
import { SUBAGENT_TOOL_NAMES } from "~/pages/workspace/utils/subagentTree.ts";

export const buildToolResultMap = (messages: ReadonlyArray<ChatMessage>): Map<string, ToolResultBlock> => {
  const map = new Map<string, ToolResultBlock>();
  for (const message of messages) {
    for (const block of message.content) {
      if (isToolResultBlock(block as BlockUnion)) {
        const resultBlock = block as ToolResultBlock;
        map.set(resultBlock.toolUseId, resultBlock);
      }
    }
  }
  return map;
};

// Only filter USER messages that contain only tool-result blocks — these are
// invisible API-format messages (the Anthropic protocol uses a user turn to
// return tool results to the model).  ASSISTANT messages may legitimately
// contain only tool-result blocks in Sculptor's format (where a completed
// tool_use is replaced in-place by its tool_result), and they should remain
// visible so the bash block or tool pill can be rendered.
export const hasOnlyToolResults = (message: ChatMessage): boolean =>
  message.role === ChatMessageRole.USER &&
  message.content.length > 0 &&
  message.content.every((block) => isToolResultBlock(block as BlockUnion));

/**
 * Returns true when an assistant message contains only subagent tool_result
 * blocks (which are skipped during rendering). These messages would produce
 * empty render groups and should not occupy a virtualizer slot.
 */
export const hasOnlySubagentResults = (message: ChatMessage): boolean =>
  message.role === ChatMessageRole.ASSISTANT &&
  message.content.length > 0 &&
  message.content.every((block) => {
    if (!isToolResultBlock(block as BlockUnion)) return false;
    const resultBlock = block as ToolResultBlock;
    return SUBAGENT_TOOL_NAMES.has(resultBlock.toolName);
  });

// Merge the completed chat messages with the queued messages for rendering,
// keeping each id at most once (first occurrence wins, so a completed/sent
// message takes precedence over a queued copy of the same id).
//
// The backend can briefly report the same id in both lists — e.g. after a
// hard-kill restart re-queues an already-promoted message (see the replay logic
// in message_conversion.py). Concatenating them blindly would render the id
// twice and emit a duplicate React key, which detaches virtualized rows and
// leaks them across agents. Deduping here keeps the rendered list well-formed
// even if a duplicate slips through.
export const mergeChatAndQueuedMessages = (
  chatMessages: ReadonlyArray<ChatMessage>,
  queuedChatMessages: ReadonlyArray<ChatMessage>,
): Array<ChatMessage> => {
  const seenIds = new Set<string>();
  const merged: Array<ChatMessage> = [];
  for (const message of [...chatMessages, ...queuedChatMessages]) {
    if (seenIds.has(message.id)) continue;
    seenIds.add(message.id);
    merged.push(message);
  }
  return merged;
};

// Same defense as mergeChatAndQueuedMessages, for the busy-agent path where the
// two lists render separately (completed in the chat, queued in the queued-message
// bar): a queued message whose id was already promoted to the completed list must
// not also appear in the bar as a stuck queued copy.
export const omitMessagesAlreadyInChat = (
  queuedChatMessages: ReadonlyArray<ChatMessage>,
  chatMessages: ReadonlyArray<ChatMessage>,
): Array<ChatMessage> => {
  const chatIds = new Set(chatMessages.map((message) => message.id));
  return queuedChatMessages.filter((message) => !chatIds.has(message.id));
};
