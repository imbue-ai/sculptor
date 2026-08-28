import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import type { SubagentTreeNode } from "~/pages/workspace/chatAlpha/utils/subagentTree.ts";
import { isToolResultBlock, isToolUseBlock } from "~/pages/workspace/utils/blockGuards.ts";
import { isHiddenTool } from "~/pages/workspace/utils/toolPredicates.ts";

/**
 * Collect all leaf (non-subagent) tool blocks from subagent child nodes.
 *
 * A "leaf" block is a ToolUseBlock that has no subagent children of its own,
 * and isn't a hidden tool. ToolResultBlocks are included only when no
 * matching ToolUseBlock was seen (result-only segments from reload).
 */
export const collectLeafToolBlocks = (
  childNodes: ReadonlyArray<SubagentTreeNode>,
): Array<ToolUseBlock | ToolResultBlock> => {
  const seenToolUseIds = new Set<string>();
  const blocks: Array<ToolUseBlock | ToolResultBlock> = [];

  for (const node of childNodes) {
    if (node.message.role === ChatMessageRole.USER) continue;

    for (const block of node.message.content) {
      if (isToolUseBlock(block)) {
        seenToolUseIds.add(block.id);
        if (isHiddenTool(block.name)) continue;
        const children = node.children.get(block.id);
        if (!children || children.length === 0) {
          blocks.push(block);
        }
      } else if (isToolResultBlock(block)) {
        if (isHiddenTool(block.toolName)) continue;
        if (!seenToolUseIds.has(block.toolUseId)) {
          blocks.push(block);
        }
      }
    }
  }

  return blocks;
};
