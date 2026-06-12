import { useMemo } from "react";

import type { ChatMessage, DiffToolContent, ToolResultBlock, ToolUseBlock } from "~/api";
import type { BlockUnion } from "~/common/Guards";
import { isDiffToolContent, isToolResultBlock, isToolUseBlock } from "~/common/Guards";
import type { SubagentTreeNode } from "~/pages/workspace/utils/subagentTree";

type FileChangeStatus = "modified" | "new" | "deleted" | "renamed";

export type TurnFile = {
  path: string;
  status: FileChangeStatus;
};

const FILE_CHANGING_TOOLS = new Set(["Edit", "Write", "MultiEdit"]);

/**
 * Collect file paths changed in a message by looking at two streaming-time sources:
 *
 * 1. ToolUseBlock inputs for file-changing tools (present during streaming
 *    before the block is replaced by its ToolResultBlock).
 * 2. DiffToolContent.filePath on successful ToolResultBlocks (present after
 *    the message is persisted, since message_conversion replaces ToolUseBlocks
 *    with their corresponding ToolResultBlocks).
 *
 * Together these cover both the streaming and post-persistence states for
 * Edit/Write/MultiEdit tools. They do NOT cover Bash-based file changes;
 * for that, use the backend-computed turnMetrics.changedFiles instead.
 *
 * Failed tool calls (isError) are excluded.
 */
const collectChangedFilePaths = (message: ChatMessage): ReadonlyArray<string> => {
  const errorToolUseIds = new Set<string>();
  for (const block of message.content) {
    if (isToolResultBlock(block as BlockUnion)) {
      const result = block as ToolResultBlock;
      if (result.isError) {
        errorToolUseIds.add(result.toolUseId);
      }
    }
  }

  const paths: Array<string> = [];
  const seen = new Set<string>();

  // Source 1: ToolUseBlock inputs (available during streaming)
  for (const block of message.content) {
    if (isToolUseBlock(block as BlockUnion)) {
      const toolUse = block as ToolUseBlock;
      if (!FILE_CHANGING_TOOLS.has(toolUse.name)) continue;
      if (errorToolUseIds.has(toolUse.id)) continue;
      const filePath = toolUse.input?.file_path;
      if (typeof filePath === "string" && !seen.has(filePath)) {
        paths.push(filePath);
        seen.add(filePath);
      }
    }
  }

  // Source 2: DiffToolContent.filePath on ToolResultBlocks (available after persistence)
  for (const block of message.content) {
    if (isToolResultBlock(block as BlockUnion)) {
      const result = block as ToolResultBlock;
      if (result.isError) continue;
      if (!result.content || !isDiffToolContent(result.content)) continue;
      const filePath = (result.content as DiffToolContent).filePath;
      if (typeof filePath === "string" && !seen.has(filePath)) {
        paths.push(filePath);
        seen.add(filePath);
      }
    }
  }

  return paths;
};

const buildTurnFiles = (paths: ReadonlyArray<string>): ReadonlyArray<TurnFile> => {
  const seen = new Set<string>();
  const files: Array<TurnFile> = [];

  for (const path of paths) {
    if (!seen.has(path)) {
      seen.add(path);
      files.push({ path, status: "modified" });
    }
  }

  return files;
};

/**
 * Collect file paths from a node and all its descendants (recursive).
 *
 * When the backend-computed changedFiles is available on turnMetrics, it is
 * used as the authoritative source (covers all tools including Bash).
 * Otherwise, falls back to the streaming-time sources (ToolUseBlock/DiffToolContent).
 */
const collectAllPaths = (node: SubagentTreeNode): Array<string> => {
  const backendFiles = node.message.turnMetrics?.changedFiles;
  const paths: Array<string> =
    backendFiles != null && backendFiles.length > 0 ? [...backendFiles] : [...collectChangedFilePaths(node.message)];

  for (const children of node.children.values()) {
    for (const childNode of children) {
      paths.push(...collectAllPaths(childNode));
    }
  }

  return paths;
};

/**
 * Compute turn summary data from an assistant message and its subagent children.
 * Returns undefined if the turn has no successful file edits.
 *
 * Uses three sources of file change information:
 * 1. turnMetrics.changedFiles (authoritative, post-turn, covers all tools)
 * 2. ToolUseBlock.input.file_path (streaming fallback, Edit/Write/MultiEdit only)
 * 3. DiffToolContent.filePath (post-persistence fallback, Edit/Write/MultiEdit only)
 */
export const useTurnSummaryData = (
  message: ChatMessage,
  node: SubagentTreeNode,
): ReadonlyArray<TurnFile> | undefined => {
  return useMemo(() => {
    const allPaths = collectAllPaths(node);

    if (allPaths.length === 0) return undefined;
    return buildTurnFiles(allPaths);
  }, [node]);
};
