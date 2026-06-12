import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ChatMessageRole } from "~/api";
import type { SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";
import { isHiddenTool } from "~/pages/workspace/utils/utils.ts";

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
      if (block.type === "tool_use") {
        const toolBlock = block as ToolUseBlock;
        seenToolUseIds.add(toolBlock.id);
        if (isHiddenTool(toolBlock.name)) continue;
        const children = node.children.get(toolBlock.id);
        if (!children || children.length === 0) {
          blocks.push(toolBlock);
        }
      } else if (block.type === "tool_result") {
        const resultBlock = block as ToolResultBlock;
        if (isHiddenTool(resultBlock.toolName)) continue;
        if (!seenToolUseIds.has(resultBlock.toolUseId)) {
          blocks.push(resultBlock);
        }
      }
    }
  }

  return blocks;
};
