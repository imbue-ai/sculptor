import type { ErrorBlock, FileBlock, ToolResultBlock, ToolUseBlock, WarningBlock } from "~/api";
import type { BlockUnion } from "~/common/Guards";
import {
  isContextClearedBlock,
  isContextSummaryBlock,
  isErrorBlock,
  isFileBlock,
  isResumeResponseBlock,
  isTextBlock,
  isToolResultBlock,
  isToolUseBlock,
  isWarningBlock,
} from "~/common/Guards";
import type { SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";
import { SUBAGENT_TOOL_NAMES } from "~/pages/workspace/utils/subagentTree.ts";
import { isAskUserQuestionTool, isExitPlanModeTool } from "~/pages/workspace/utils/utils.ts";

export type RenderGroup =
  | { type: "text"; blocks: Array<{ text: string }> }
  | { type: "tools"; blocks: Array<ToolUseBlock | ToolResultBlock> }
  | { type: "files"; blocks: Array<FileBlock> }
  | { type: "error"; block: ErrorBlock }
  | { type: "warning"; block: WarningBlock }
  | { type: "context_summary"; text: string }
  | { type: "context_cleared"; text: string }
  | { type: "resume_response" };

const isSpecialToolUse = (block: ToolUseBlock): boolean =>
  isAskUserQuestionTool(block.name) || isExitPlanModeTool(block.name);

export const buildRenderGroups = (
  content: ReadonlyArray<BlockUnion>,
  nodeChildren: Map<string, Array<SubagentTreeNode>>,
): Array<RenderGroup> => {
  const groups: Array<RenderGroup> = [];
  let currentTextBlocks: Array<{ text: string }> = [];
  let currentToolBlocks: Array<ToolUseBlock | ToolResultBlock> = [];

  const flushText = (): void => {
    if (currentTextBlocks.length > 0) {
      groups.push({ type: "text", blocks: currentTextBlocks });
      currentTextBlocks = [];
    }
  };

  const flushTools = (): void => {
    if (currentToolBlocks.length > 0) {
      groups.push({ type: "tools", blocks: currentToolBlocks });
      currentToolBlocks = [];
    }
  };

  const flush = (): void => {
    flushText();
    flushTools();
  };

  for (const block of content) {
    if (isTextBlock(block)) {
      if (currentToolBlocks.length > 0) flushTools();
      currentTextBlocks.push(block as { text: string });
    } else if (isToolUseBlock(block) || isToolResultBlock(block)) {
      if (currentTextBlocks.length > 0) flushText();

      // Isolate AskUserQuestion and ExitPlanMode tool_use blocks
      const isIsolated = isToolUseBlock(block) && isSpecialToolUse(block as ToolUseBlock);

      // Skip subagent tool_result blocks — their content is rendered
      // inside the AlphaSubagentPill via subagentMetadataMap.
      // Check both tree structure (children exist) and tool name so that
      // Agent/Task results are hidden even when the ToolResultBlock ends up
      // in a different message from the original ToolUseBlock.
      const isSubagentResult =
        isToolResultBlock(block) &&
        (SUBAGENT_TOOL_NAMES.has((block as ToolResultBlock).toolName) ||
          (nodeChildren.has((block as ToolResultBlock).toolUseId) &&
            (nodeChildren.get((block as ToolResultBlock).toolUseId)?.length ?? 0) > 0));

      if (isSubagentResult) continue;

      // Subagent tool_use blocks (Agent/Task) are NOT isolated here. When
      // the LLM emits parallel tools alongside an Agent call in one message
      // — e.g. [Bash, Bash, Agent, Bash, Bash] — isolating the Agent block
      // split the surrounding Bash blocks into two separate pill rows,
      // breaking the grouping the user expects (SCU-1139). Keep all tools
      // in one render group; ToolBlockGroup pulls subagent blocks out and
      // renders the AlphaSubagentPill above the surrounding pill row.
      if (isIsolated && currentToolBlocks.length > 0) {
        flushTools();
      }
      currentToolBlocks.push(block as ToolUseBlock | ToolResultBlock);
      if (isIsolated) {
        flushTools();
      }
    } else if (isErrorBlock(block)) {
      flush();
      groups.push({ type: "error", block: block as ErrorBlock });
    } else if (isWarningBlock(block)) {
      flush();
      groups.push({ type: "warning", block: block as WarningBlock });
    } else if (isContextSummaryBlock(block)) {
      flush();
      groups.push({ type: "context_summary", text: (block as { text: string }).text });
    } else if (isContextClearedBlock(block)) {
      flush();
      groups.push({ type: "context_cleared", text: (block as { text?: string }).text ?? "Cleared successfully" });
    } else if (isResumeResponseBlock(block)) {
      flush();
      groups.push({ type: "resume_response" });
    } else if (isFileBlock(block)) {
      flush();
      const lastGroup = groups[groups.length - 1];
      if (lastGroup?.type === "files") {
        lastGroup.blocks.push(block as FileBlock);
      } else {
        groups.push({ type: "files", blocks: [block as FileBlock] });
      }
    }
  }

  flush();
  return groups;
};
