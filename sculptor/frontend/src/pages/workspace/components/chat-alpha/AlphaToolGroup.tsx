import type { ReactElement } from "react";
import { useMemo } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { isToolUseBlock } from "~/common/Guards";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import {
  useTaskSupportsInteractiveBackchannel,
  useTaskSupportsSubAgents,
} from "~/common/state/hooks/useTaskHelpers.ts";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";
import { SUBAGENT_TOOL_NAMES } from "~/pages/workspace/utils/subagentTree.ts";
import { isEnterPlanModeTool, isHiddenTool } from "~/pages/workspace/utils/utils.ts";

import { AlphaAskUserQuestionBlock } from "./AlphaAskUserQuestionBlock.tsx";
import { AlphaExitPlanModeBlock } from "./AlphaExitPlanModeBlock.tsx";
import { AlphaSubagentPill } from "./AlphaSubagentPill.tsx";
import { CompletedToolLine, ToolLine } from "./AlphaToolLines.tsx";
import { AlphaWorkflowPill } from "./AlphaWorkflowPill.tsx";
import { renderToolSegments } from "./renderToolSegments.tsx";
import { ToolNavigationProvider } from "./ToolNavigationContext.tsx";

const WORKFLOW_TOOL_NAME = "Workflow";

// The Workflow tool renders as its own subagent-style pill. Both block
// shapes must route there: the live tool_use, and the bare tool_result left
// behind when a finalized streamed message result-replaces the tool_use.
type WorkflowBlockRef = {
  toolUseId: string;
  block?: ToolUseBlock;
  result?: ToolResultBlock;
};

const getToolName = (block: ToolUseBlock | ToolResultBlock): string =>
  block.type === "tool_use" ? block.name : (block as ToolResultBlock).toolName;

const isTopLevelToolBlock = (block: ToolUseBlock | ToolResultBlock): boolean => {
  const toolName = getToolName(block);
  return isEnterPlanModeTool(toolName);
};

// The harness stamps interactiveRole on backchannel tool blocks (server-side,
// from Harness.classify_tool_ui_role) so rendering keys off the role rather than
// a hardcoded set of tool names — each harness owns which of its tools are
// ask-user-question / exit-plan-mode.
const isSpecialToolUse = (block: ToolUseBlock): boolean => block.interactiveRole != null;

// AUQ / ExitPlanMode tool_result blocks are consumed by the inline
// AlphaAskUserQuestionBlock / AlphaExitPlanModeBlock via the
// submittedQuestionAnswers lookup. Rendering them as a separate generic
// tool-call card would duplicate what the inline block already shows.
const isSpecialToolResult = (block: ToolUseBlock | ToolResultBlock): boolean =>
  block.type === "tool_result" && block.interactiveRole != null;

export const ToolBlockGroup = ({
  blocks,
  node,
  toolResultMap,
  subagentMetadataMap,
  inProgressMessageId,
  isActive,
}: {
  blocks: Array<ToolUseBlock | ToolResultBlock>;
  node: SubagentTreeNode;
  toolResultMap: Map<string, ToolResultBlock>;
  subagentMetadataMap: Map<string, SubagentMetadata>;
  inProgressMessageId?: string | null;
  isActive: boolean;
}): ReactElement => {
  const { agentID: taskID } = useWorkspacePageParams();
  // Per-harness gates centralized here so the leaf components stay test-isolated:
  //   `supportsSubAgents` hides the AlphaSubagentPill
  //   `supportsInteractiveBackchannel` hides AlphaAskUserQuestionBlock + AlphaExitPlanModeBlock
  // `?? true` preserves existing Claude behavior while the task is still loading.
  const canRenderSubAgents = useTaskSupportsSubAgents(taskID ?? "") ?? true;
  const canRenderInteractiveBackchannel = useTaskSupportsInteractiveBackchannel(taskID ?? "") ?? true;
  // Separate blocks into subagent, workflow, top-level, special, and regular categories
  const { subagentBlocks, workflowBlocks, topLevelBlocks, specialBlocks, regularBlocks } = useMemo(() => {
    const subagent: Array<ToolUseBlock> = [];
    const workflowByToolUseId = new Map<string, WorkflowBlockRef>();
    const topLevel: Array<ToolUseBlock | ToolResultBlock> = [];
    const special: Array<ToolUseBlock> = [];
    const regular: Array<ToolUseBlock | ToolResultBlock> = [];

    for (const block of blocks) {
      if (isHiddenTool(getToolName(block))) continue;
      if (isSpecialToolResult(block)) continue;

      if (isToolUseBlock(block)) {
        const children = node.children.get(block.id);
        if (block.name === WORKFLOW_TOOL_NAME) {
          workflowByToolUseId.set(block.id, { ...workflowByToolUseId.get(block.id), toolUseId: block.id, block });
        } else if (SUBAGENT_TOOL_NAMES.has(block.name) || (children && children.length > 0)) {
          subagent.push(block);
        } else if (isSpecialToolUse(block)) {
          special.push(block);
        } else if (isTopLevelToolBlock(block)) {
          topLevel.push(block);
        } else {
          regular.push(block);
        }
      } else if (isTopLevelToolBlock(block)) {
        topLevel.push(block);
      } else {
        // Skip tool_result blocks that belong to subagent tool calls —
        // their content is already rendered inside the AlphaSubagentPill.
        // Check both tree structure and tool name so results are hidden
        // even when the ToolResultBlock is in a different message.
        if (SUBAGENT_TOOL_NAMES.has(block.toolName)) continue;
        if (block.toolName === WORKFLOW_TOOL_NAME) {
          const existing = workflowByToolUseId.get(block.toolUseId);
          workflowByToolUseId.set(block.toolUseId, { ...existing, toolUseId: block.toolUseId, result: block });
          continue;
        }
        const toolUseId = block.toolUseId;
        const children = toolUseId ? node.children.get(toolUseId) : undefined;
        if (children && children.length > 0) continue;

        regular.push(block);
      }
    }

    return {
      subagentBlocks: subagent,
      workflowBlocks: Array.from(workflowByToolUseId.values()),
      topLevelBlocks: topLevel,
      specialBlocks: special,
      regularBlocks: regular,
    };
  }, [blocks, node.children]);

  return (
    <ToolNavigationProvider>
      {canRenderSubAgents &&
        subagentBlocks.map((block, index) => {
          const children = node.children.get(block.id) ?? [];
          return (
            <AlphaSubagentPill
              key={block.id}
              rowIndex={index}
              parentBlock={block}
              childNodes={children}
              toolResultMap={toolResultMap}
              subagentMetadataMap={subagentMetadataMap}
            />
          );
        })}
      {workflowBlocks.map((workflow, index) => (
        <AlphaWorkflowPill
          key={workflow.toolUseId}
          rowIndex={subagentBlocks.length + index}
          toolUseId={workflow.toolUseId}
          block={workflow.block}
          result={workflow.result ?? toolResultMap.get(workflow.toolUseId)}
        />
      ))}
      {canRenderInteractiveBackchannel &&
        specialBlocks.map((block) => {
          if (block.interactiveRole === "ask_user_question") {
            return <AlphaAskUserQuestionBlock key={block.id} toolBlock={block} />;
          }

          if (block.interactiveRole === "exit_plan_mode") {
            return <AlphaExitPlanModeBlock key={block.id} toolBlock={block} />;
          }
          return null;
        })}
      {topLevelBlocks.map((block) => {
        if (isToolUseBlock(block)) {
          const isExecuting = inProgressMessageId != null && !toolResultMap.has(block.id);
          return (
            <ToolLine key={block.id} block={block} result={toolResultMap.get(block.id)} isExecuting={isExecuting} />
          );
        }
        return <CompletedToolLine key={block.toolUseId} block={block} />;
      })}
      {renderToolSegments(regularBlocks, toolResultMap, {
        isActive,
        inProgressMessageId: inProgressMessageId ?? null,
        // Only subagent and workflow pills above register with the nav context
        // (one row each); top-level/special blocks render inline and don't
        // participate in arrow-key navigation, so they don't shift the offset.
        rowIndexOffset: subagentBlocks.length + workflowBlocks.length,
      })}
    </ToolNavigationProvider>
  );
};
