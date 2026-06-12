import type { ToolResultBlock, ToolUseBlock } from "~/api";

import type { PillData, PillState } from "./toolPill.types.ts";

export type RelativePath = {
  /** Path string to display. Workspace prefix stripped when applicable. */
  display: string;
  /** True when the path is absolute and lives outside the workspace code path. */
  isOutsideWorkspace: boolean;
};

const isAbsolutePath = (p: string): boolean => p.startsWith("/") || /^[a-zA-Z]:[\\/]/.test(p);

/**
 * Strip the workspace code path prefix from an absolute path, returning a
 * project-relative path. When the path is absolute but doesn't sit under the
 * workspace, returns the full path with `isOutsideWorkspace: true` so callers
 * can flag it visually. Relative paths are returned as-is.
 */
export const makeRelative = (filePath: string, workspaceCodePath: string | null): RelativePath => {
  if (workspaceCodePath) {
    const prefix = workspaceCodePath.endsWith("/") ? workspaceCodePath : `${workspaceCodePath}/`;
    if (filePath.startsWith(prefix)) return { display: filePath.slice(prefix.length), isOutsideWorkspace: false };
    if (filePath === workspaceCodePath) return { display: "", isOutsideWorkspace: false };
  }

  if (isAbsolutePath(filePath)) {
    return { display: filePath, isOutsideWorkspace: true };
  }
  return { display: filePath, isOutsideWorkspace: false };
};

const getPillStateFromResult = (
  hasResult: boolean,
  isError: boolean,
  inProgressMessageId: string | null,
): PillState => {
  if (!hasResult && inProgressMessageId !== null) return "initializing";
  if (isError) return "error";
  return "completed";
};

/**
 * Build pill data from a list of tool blocks. Always produces one pill per
 * tool call — there is no summary/grouping. Each pill carries the data
 * needed to render its own popover.
 *
 * Also handles `ToolResultBlock`-only segments (when the backend replaces
 * tool_use with tool_result in completed messages). When the same tool call
 * appears as both shapes in `blocks` — which can happen during the streaming
 * transition into the result-replaced form — the tool_use side wins and the
 * matching tool_result is dropped, so the pill renders once.
 */
export const buildPillData = (
  blocks: ReadonlyArray<ToolUseBlock | ToolResultBlock>,
  toolResultMap: Map<string, ToolResultBlock>,
  inProgressMessageId: string | null,
): ReadonlyArray<PillData> => {
  const toolUseIds = new Set<string>();
  for (const block of blocks) {
    if (block.type === "tool_use") toolUseIds.add(block.id);
  }

  const pills: Array<PillData> = [];

  for (const block of blocks) {
    if (block.type === "tool_use") {
      const result = toolResultMap.get(block.id);
      const results = result ? [result] : [];
      const state = getPillStateFromResult(result !== undefined, result?.isError ?? false, inProgressMessageId);
      pills.push({
        id: block.id,
        label: block.name,
        state,
        blocks: [block],
        results,
      });
    } else {
      const resultBlock = block as ToolResultBlock;
      if (toolUseIds.has(resultBlock.toolUseId)) continue;
      pills.push({
        id: resultBlock.toolUseId,
        label: resultBlock.toolName ?? "tool",
        state: resultBlock.isError ? "error" : "completed",
        blocks: [],
        results: [resultBlock],
      });
    }
  }

  return pills;
};
