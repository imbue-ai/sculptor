import type { ChatMessage } from "../../../../api";
import type { BlockUnion } from "../../utils/blockGuards.ts";
import { isToolResultBlock, isToolUseBlock } from "../../utils/blockGuards.ts";

/**
 * A node in the subagent tree. Each node wraps a ChatMessage and contains
 * child messages belonging to subagents it spawned via Task tool calls.
 */
export type SubagentTreeNode = {
  /** The ChatMessage at this level */
  message: ChatMessage;
  /**
   * Map from tool_use_id (of a Task ToolUseBlock in this message's content)
   * to the ordered list of child SubagentTreeNodes belonging to that subagent.
   */
  children: Map<string, Array<SubagentTreeNode>>;
};

/**
 * Extract the tool_use_id from a content block, if it is a tool_use or tool_result block.
 */
export const getToolUseId = (block: ChatMessage["content"][number]): string | undefined => {
  if (isToolUseBlock(block)) {
    return block.id;
  }

  if (isToolResultBlock(block)) {
    return block.toolUseId;
  }
  return undefined;
};

/**
 * Build a tree from a flat list of ChatMessages using parentToolUseId to determine nesting.
 *
 * Messages without parentToolUseId are top-level (main agent).
 * Messages with parentToolUseId are children of the message containing the
 * ToolUseBlock/ToolResultBlock with that id.
 *
 * Supports multi-level nesting (subagents spawning sub-subagents).
 */
export const buildSubagentTree = (messages: ReadonlyArray<ChatMessage>): Array<SubagentTreeNode> => {
  const topLevel: Array<SubagentTreeNode> = [];

  // Group child messages by their parentToolUseId
  const childrenByParentToolUseId = new Map<string, Array<SubagentTreeNode>>();

  for (const message of messages) {
    const node: SubagentTreeNode = { message, children: new Map() };
    const parentId = message.parentToolUseId;

    if (parentId) {
      if (!childrenByParentToolUseId.has(parentId)) {
        childrenByParentToolUseId.set(parentId, []);
      }
      childrenByParentToolUseId.get(parentId)!.push(node);
    } else {
      topLevel.push(node);
    }
  }

  // Attach children to their parent nodes by matching ToolUseBlock/ToolResultBlock IDs
  attachChildren(topLevel, childrenByParentToolUseId);

  return topLevel;
};

const attachChildren = (
  nodes: Array<SubagentTreeNode>,
  childrenByParentToolUseId: Map<string, Array<SubagentTreeNode>>,
): void => {
  for (const node of nodes) {
    for (const block of node.message.content) {
      const toolUseId = getToolUseId(block);
      if (toolUseId) {
        const children = childrenByParentToolUseId.get(toolUseId);
        if (children) {
          node.children.set(toolUseId, children);
          // Recurse for multi-level nesting
          attachChildren(children, childrenByParentToolUseId);
        }
      }
    }
  }
};

export type SubagentMetadata = {
  subagentType?: string;
  prompt?: string;
  responseText?: string;
  /** True when the Agent tool_use had run_in_background=true. The immediate
   *  "Async agent launched" tool_result is then internal book-keeping rather
   *  than the agent's real response; the response and run time come from the
   *  subagent's own child messages instead. */
  isBackground?: boolean;
  /** Subagent run time in seconds. For background agents this is derived from
   *  the timestamp delta between the parent message and the subagent's reply,
   *  because the launch-ack tool_result's durationSeconds is ~0. */
  durationSeconds?: number;
};

/**
 * Tool names used by the Claude Code SDK for the subagent/Agent tool.
 * The tool was renamed from "Task" to "Agent"; we accept both for
 * backward compatibility with persisted sessions.
 */
export const SUBAGENT_TOOL_NAMES = new Set(["Task", "Agent"]);

/**
 * Extract clean text from a tool result content string.
 *
 * Task tool results are stored as `str()` of a Python list of content blocks, e.g.:
 *   [{'type': 'text', 'text': 'Hello world'}, {'type': 'text', 'text': 'agentId: abc123'}]
 *
 * Python's str() uses single quotes by default, but switches to double quotes when a
 * string contains apostrophes (e.g., "agent's"). This function handles both quoting
 * styles by matching the `'text':` key followed by either quote style.
 */
export const extractTextFromToolContent = (raw: string): string => {
  // Match 'text': followed by either a single-quoted or double-quoted string value.
  // Single-quoted: 'text': '...' where \' is an escaped apostrophe
  // Double-quoted: 'text': "..." where \" is an escaped double quote (used when value contains apostrophes)
  const pattern = /'text':\s*(?:'((?:[^'\\]|\\.)*?)'|"((?:[^"\\]|\\.)*?)")/g;
  const textParts: Array<string> = [];
  let match;

  while ((match = pattern.exec(raw)) !== null) {
    // match[1] is the single-quoted capture, match[2] is the double-quoted capture
    const text = (match[1] ?? match[2])
      .replace(/\\'/g, "'")
      .replace(/\\"/g, '"')
      .replace(/\\n/g, "\n")
      .replace(/\\t/g, "\t")
      .replace(/\\\\/g, "\\");

    // Filter out metadata blocks like "agentId: ..."
    if (!text.startsWith("agentId:")) {
      textParts.push(text);
    }
  }

  if (textParts.length > 0) {
    return textParts.join("");
  }

  return raw;
};

type MetadataBuilderMessage = {
  content: Array<{ type?: string; [key: string]: unknown }>;
  parentToolUseId?: string | null;
  approximateCreationTime?: string;
};

/**
 * Build a map of toolUseId → SubagentMetadata by scanning all messages for Task tool_use
 * and tool_result blocks. This gives us the prompt (from tool_use input) and response
 * (from tool_result content) for each subagent invocation.
 *
 * Background Agent tool_uses (run_in_background=true) get special handling: their
 * immediate "Async agent launched" tool_result is internal book-keeping, so we ignore
 * it and instead derive responseText + durationSeconds from the subagent's own child
 * messages (parentToolUseId === the Agent's tool_use id).
 */
export const buildSubagentMetadataMap = (messages: Array<MetadataBuilderMessage>): Map<string, SubagentMetadata> => {
  const map = new Map<string, SubagentMetadata>();
  // toolUseId → creation time of the message that contained the Agent tool_use.
  // Used to compute background subagent run time from the subagent's reply time.
  const parentStartTime = new Map<string, number>();

  // First pass: tool_use / tool_result blocks inside each message.
  for (const message of messages) {
    const messageCreatedMs = parseTimestampMs(message.approximateCreationTime);
    for (const block of message.content) {
      if (block.type === "tool_use" && SUBAGENT_TOOL_NAMES.has(block.name as string)) {
        const input = block.input as Record<string, unknown> | undefined;
        const isBackground = input?.run_in_background === true;
        const metadata: SubagentMetadata = {
          subagentType: typeof input?.subagent_type === "string" ? input.subagent_type : undefined,
          prompt: typeof input?.prompt === "string" ? input.prompt : undefined,
        };
        if (isBackground) {
          metadata.isBackground = true;
        }
        const toolUseId = block.id as string;
        map.set(toolUseId, metadata);
        if (messageCreatedMs !== null) {
          parentStartTime.set(toolUseId, messageCreatedMs);
        }
      } else if (block.type === "tool_result") {
        const toolUseId = block.toolUseId as string | undefined;
        if (toolUseId && map.has(toolUseId)) {
          const existing = map.get(toolUseId)!;
          // Background agents' immediate tool_result is the launch-ack
          // ("Async agent launched...") — internal book-keeping, not the
          // subagent's response. Skip it; the real response is filled in
          // from the subagent's child messages in the second pass below.
          if (existing.isBackground) continue;
          const content = block.content as { contentType?: string; text?: string } | undefined;
          if (content && content.contentType === "generic" && typeof content.text === "string") {
            existing.responseText = extractTextFromToolContent(content.text);
          }
        }
      }
    }
  }

  // Second pass: for background agents, walk the subagent's child messages
  // (parentToolUseId === the Agent's tool_use id) to get the real response
  // text and to measure run time from the timestamp delta. The latest-by-
  // timestamp child message with non-empty text wins, so we stay stable
  // when streaming partials or reconnect-replays arrive out of order.
  const latestChildMs = new Map<string, number>();
  for (const message of messages) {
    const parentId = message.parentToolUseId;
    if (!parentId) continue;
    const existing = map.get(parentId);
    if (!existing?.isBackground) continue;
    const text = extractMessageText(message.content);
    if (text.length === 0) continue;
    const endMs = parseTimestampMs(message.approximateCreationTime);
    const prevEndMs = latestChildMs.get(parentId);
    // Skip if a strictly later sibling already won. Messages without
    // timestamps can't refute a timestamped winner, so they're skipped too.
    if (endMs !== null && prevEndMs !== undefined && endMs < prevEndMs) continue;
    if (endMs === null && prevEndMs !== undefined) continue;
    existing.responseText = text;
    if (endMs !== null) {
      latestChildMs.set(parentId, endMs);
      const startMs = parentStartTime.get(parentId);
      if (startMs !== undefined && endMs > startMs) {
        existing.durationSeconds = (endMs - startMs) / 1000;
      }
    }
  }

  return map;
};

const parseTimestampMs = (raw: string | undefined): number | null => {
  if (typeof raw !== "string" || raw.length === 0) return null;
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : null;
};

const extractMessageText = (content: ReadonlyArray<{ type?: string; [key: string]: unknown }>): string => {
  const parts: Array<string> = [];
  for (const block of content) {
    if (block.type === "text" && typeof block.text === "string") {
      parts.push(block.text as string);
    }
  }
  return parts.join("");
};

/**
 * Check if a message has any visible content beyond subagent tool blocks.
 *
 * Returns false when every tool_use/tool_result block in the message is a subagent
 * parent (i.e., has subagent children). Text blocks alone don't count as visible
 * when all tools are subagent launches, because on reload the main agent's text can
 * end up in the same message as the subagent tool_use blocks (while during streaming
 * it ends up in a later message). This prevents the action bar from appearing in the
 * wrong position.
 *
 * Returns true when the message has non-subagent tool blocks, error/warning blocks,
 * or text blocks without any subagent tool blocks.
 */
export const hasVisibleToolContent = (
  contentBlocks: Array<BlockUnion>,
  subagentChildren?: Map<string, Array<SubagentTreeNode>>,
): boolean => {
  let hasText = false;
  let hasSubagentTool = false;
  let hasNonSubagentContent = false;

  for (const block of contentBlocks) {
    if (block.type === "text") {
      hasText = true;
    } else if (isToolUseBlock(block)) {
      const children = block.id ? subagentChildren?.get(block.id) : undefined;
      if (children && children.length > 0) {
        hasSubagentTool = true;
      } else {
        hasNonSubagentContent = true;
      }
    } else if (isToolResultBlock(block)) {
      // Subagent tool_result blocks are phantom content (filtered during rendering).
      // Check both tool name and tree children to catch all cases.
      const isSubagentByName = SUBAGENT_TOOL_NAMES.has(block.toolName);
      const toolUseId = block.toolUseId;
      const children = toolUseId ? subagentChildren?.get(toolUseId) : undefined;
      if (!isSubagentByName && (!children || children.length === 0)) {
        hasNonSubagentContent = true;
      }
    } else {
      // Any other block type (error, warning, etc.) is visible
      hasNonSubagentContent = true;
    }
  }

  if (hasNonSubagentContent) {
    return true;
  }

  // Text is only visible when there are no subagent tool blocks in the message.
  // When subagent tools are present, the text is introductory reasoning for the
  // subagent launches and the action bar should appear on a later message instead.
  if (hasText && !hasSubagentTool) {
    return true;
  }
  return false;
};
