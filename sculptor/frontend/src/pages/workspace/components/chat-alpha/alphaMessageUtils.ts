import type { ChatMessage, ToolResultBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import { isToolResultBlock } from "~/common/Guards";
import { SUBAGENT_TOOL_NAMES, type SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";

// Memoize by input-array reference. On an agent switch the chat view remounts
// and rebuilds this from scratch; when the message array keeps its reference
// (idle agent, no queued messages — see mergeChatAndQueuedMessages), the
// remount reuses the prior map instead of re-scanning O(history). WeakMap
// entries are GC'd with their input array, so nothing leaks.
const toolResultMapCache = new WeakMap<ReadonlyArray<ChatMessage>, Map<string, ToolResultBlock>>();

export const buildToolResultMap = (messages: ReadonlyArray<ChatMessage>): Map<string, ToolResultBlock> => {
  const cached = toolResultMapCache.get(messages);
  if (cached) return cached;
  const map = new Map<string, ToolResultBlock>();
  for (const message of messages) {
    for (const block of message.content) {
      if (isToolResultBlock(block)) {
        map.set(block.toolUseId, block);
      }
    }
  }
  toolResultMapCache.set(messages, map);
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
  message.content.every((block) => isToolResultBlock(block));

/**
 * Returns true when an assistant message contains only subagent tool_result
 * blocks (which are skipped during rendering). These messages would produce
 * empty render groups and should not occupy a virtualizer slot.
 */
export const hasOnlySubagentResults = (message: ChatMessage): boolean =>
  message.role === ChatMessageRole.ASSISTANT &&
  message.content.length > 0 &&
  message.content.every((block) => {
    if (!isToolResultBlock(block)) return false;
    return SUBAGENT_TOOL_NAMES.has(block.toolName);
  });

// Drop tool-result-only / subagent-result-only nodes so they don't occupy a
// virtualizer slot. Memoized by the tree reference: when buildSubagentTree
// returns its cached tree on a remount, the filtered list is reused too.
const filteredNodesCache = new WeakMap<Array<SubagentTreeNode>, Array<SubagentTreeNode>>();

export const filterRenderableNodes = (nodes: Array<SubagentTreeNode>): Array<SubagentTreeNode> => {
  const cached = filteredNodesCache.get(nodes);
  if (cached) return cached;
  const result = nodes.filter((node) => !hasOnlyToolResults(node.message) && !hasOnlySubagentResults(node.message));
  filteredNodesCache.set(nodes, result);
  return result;
};

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
  // Fast path: nothing queued (the common case). Return the input as-is so its
  // reference stays stable across renders/remounts — completedChatMessages is
  // already deduped upstream, so there is nothing to merge. A stable reference
  // is what lets the reference-keyed builder caches (tree / tool-result map /
  // metadata / filtered nodes) hit on remount instead of recomputing O(history).
  if (queuedChatMessages.length === 0) {
    return chatMessages as Array<ChatMessage>;
  }

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
