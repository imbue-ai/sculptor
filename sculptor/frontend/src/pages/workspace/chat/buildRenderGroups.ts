import type { ErrorBlock, FileBlock, ToolResultBlock, ToolUseBlock, WarningBlock } from "~/api";
import type { SubagentTreeNode } from "~/pages/workspace/chat/utils/subagentTree.ts";
import { SUBAGENT_TOOL_NAMES } from "~/pages/workspace/chat/utils/subagentTree.ts";
import type { BlockUnion } from "~/pages/workspace/utils/blockGuards";
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
} from "~/pages/workspace/utils/blockGuards";

export type RenderGroup =
  | { type: "text"; blocks: Array<{ text: string }> }
  | { type: "tools"; blocks: Array<ToolUseBlock | ToolResultBlock> }
  | { type: "files"; blocks: Array<FileBlock> }
  | { type: "error"; block: ErrorBlock }
  | { type: "warning"; block: WarningBlock }
  | { type: "context_summary"; text: string }
  | { type: "context_cleared"; text: string }
  | { type: "resume_response" };

// Backchannel tools (ask-user-question / exit-plan-mode) are isolated into their
// own render group so they render as the inline question/plan panel. The harness
// stamps `interactiveRole` server-side, so this is harness-agnostic.
const isSpecialToolUse = (block: ToolUseBlock): boolean => block.interactiveRole != null;

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
      currentTextBlocks.push(block);
    } else if (isToolUseBlock(block) || isToolResultBlock(block)) {
      if (currentTextBlocks.length > 0) flushText();

      // Isolate AskUserQuestion and ExitPlanMode tool_use blocks
      const isIsolated = isToolUseBlock(block) && isSpecialToolUse(block);

      // Skip subagent tool_result blocks — their content is rendered
      // inside the SubagentPill via subagentMetadataMap.
      // Check both tree structure (children exist) and tool name so that
      // Agent/Task results are hidden even when the ToolResultBlock ends up
      // in a different message from the original ToolUseBlock.
      const isSubagentResult =
        isToolResultBlock(block) &&
        (SUBAGENT_TOOL_NAMES.has(block.toolName) ||
          (nodeChildren.has(block.toolUseId) && (nodeChildren.get(block.toolUseId)?.length ?? 0) > 0));

      if (isSubagentResult) continue;

      // Subagent tool_use blocks (Agent/Task) are NOT isolated here. When
      // the LLM emits parallel tools alongside an Agent call in one message
      // — e.g. [Bash, Bash, Agent, Bash, Bash] — isolating the Agent block
      // split the surrounding Bash blocks into two separate pill rows,
      // breaking the grouping the user expects (SCU-1139). Keep all tools
      // in one render group; ToolBlockGroup pulls subagent blocks out and
      // renders the SubagentPill above the surrounding pill row.
      if (isIsolated && currentToolBlocks.length > 0) {
        flushTools();
      }
      currentToolBlocks.push(block);
      if (isIsolated) {
        flushTools();
      }
    } else if (isErrorBlock(block)) {
      flush();
      groups.push({ type: "error", block });
    } else if (isWarningBlock(block)) {
      flush();
      groups.push({ type: "warning", block });
    } else if (isContextSummaryBlock(block)) {
      flush();
      groups.push({ type: "context_summary", text: block.text });
    } else if (isContextClearedBlock(block)) {
      flush();
      groups.push({ type: "context_cleared", text: block.text ?? "Cleared successfully" });
    } else if (isResumeResponseBlock(block)) {
      flush();
      groups.push({ type: "resume_response" });
    } else if (isFileBlock(block)) {
      flush();
      const lastGroup = groups[groups.length - 1];
      if (lastGroup?.type === "files") {
        lastGroup.blocks.push(block);
      } else {
        groups.push({ type: "files", blocks: [block] });
      }
    }
  }

  flush();
  return groups;
};
