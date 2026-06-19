import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { isDiffToolContent, isGenericToolContent } from "~/common/Guards.ts";
import { getLineCounts } from "~/components/DiffUtils.ts";
import { isDiffTool } from "~/pages/workspace/utils/utils.ts";

import type { ChipData, ChipState, Segment } from "./chipRow.types.ts";

type BlockInfo = {
  block: ToolUseBlock;
  result: ToolResultBlock | undefined;
  filePath: string;
  state: ChipState;
};

/**
 * Extract the file path from a tool block.
 * Prefers the result's filePath (from DiffToolContent) when available,
 * falls back to block.input.file_path for executing tools.
 * Returns null if the path cannot be determined.
 */
export const getFilePathFromToolBlock = (block: ToolUseBlock, result?: ToolResultBlock): string | null => {
  if (result && isDiffToolContent(result.content)) {
    return result.content.filePath;
  }

  if (typeof block.input?.file_path === "string") {
    return block.input.file_path;
  }
  return null;
};

/**
 * Compute disambiguated display names for a list of file paths.
 * Paths with unique basenames display as just the basename.
 * Paths sharing a basename get the minimum unique parent prefix prepended
 * as `parentDir/.../basename`. If even the full path isn't unique, the
 * full path is used as-is.
 */
export const disambiguateFileNames = (filePaths: ReadonlyArray<string>): Map<string, string> => {
  const result = new Map<string, string>();
  if (filePaths.length === 0) return result;

  const basename = (path: string): string => {
    const parts = path.split("/");
    return parts[parts.length - 1] || path;
  };

  // Group paths by basename
  const groups = new Map<string, Array<string>>();
  for (const path of filePaths) {
    const base = basename(path);
    const group = groups.get(base);
    if (group) {
      group.push(path);
    } else {
      groups.set(base, [path]);
    }
  }

  for (const [base, paths] of groups) {
    // Two mentions of the same file aren't really a collision — they point at
    // the same thing. Dedupe before disambiguating so identical paths render
    // as the bare basename instead of expanding to the full path.
    const distinctPaths = Array.from(new Set(paths));

    if (distinctPaths.length === 1) {
      result.set(paths[0], base);
      continue;
    }

    // For duplicate basenames, find minimum unique prefix.
    // Split each path into segments and walk from the end.
    const segmentsList = distinctPaths.map((p) => p.split("/"));

    for (let i = 0; i < distinctPaths.length; i++) {
      const segments = segmentsList[i];
      let isFound = false;

      for (let depth = 2; depth <= segments.length; depth++) {
        const candidate = segments.slice(segments.length - depth).join("/");
        const isUnique = segmentsList.every((otherSegments, j) => {
          if (j === i) return true;
          if (otherSegments.length < depth) return true;
          const otherCandidate = otherSegments.slice(otherSegments.length - depth).join("/");
          return otherCandidate !== candidate;
        });
        if (isUnique) {
          const parentDir = segments[segments.length - depth];
          result.set(distinctPaths[i], `${parentDir}/.../${base}`);
          isFound = true;
          break;
        }
      }

      if (!isFound) {
        result.set(distinctPaths[i], distinctPaths[i]);
      }
    }
  }

  return result;
};

/**
 * Build ChipData from a list of file-change tool blocks.
 * Handles same-file merging: blocks targeting the same file
 * are merged into one chip when all share the same terminal state,
 * or split when terminal states diverge.
 */
export const buildChipData = (
  blocks: ReadonlyArray<ToolUseBlock>,
  toolResultMap: Map<string, ToolResultBlock>,
  inProgressMessageId: string | null,
): ReadonlyArray<ChipData> => {
  const blockInfos: Array<BlockInfo> = [];
  const seenIds = new Set<string>();
  for (const block of blocks) {
    // Dedupe by block id: during the streaming transition into Sculptor's
    // result-replaced form, segmentToolBlocks can emit both the real
    // tool_use and a shim derived from the matching tool_result for the
    // same call. Walking both would fetch the same result twice and
    // double the merged chip's line counts.
    if (seenIds.has(block.id)) continue;

    const result = toolResultMap.get(block.id);
    const filePath = getFilePathFromToolBlock(block, result);
    // Only mark the id as seen once we've accepted a usable info, so a real
    // tool_use that can't yet derive a filePath does not shadow a later
    // shim with the same id that can.
    if (filePath === null) continue;
    seenIds.add(block.id);

    let state: ChipState;
    if (!result && inProgressMessageId !== null) {
      state = "executing";
    } else if (result?.isError) {
      state = "error";
    } else {
      state = "completed";
    }

    blockInfos.push({ block, result, filePath, state });
  }

  // 2. Group by filePath (preserving document order via first occurrence)
  const fileGroups = new Map<string, Array<BlockInfo>>();
  const fileOrder: Array<string> = [];
  for (const info of blockInfos) {
    const existing = fileGroups.get(info.filePath);
    if (existing) {
      existing.push(info);
    } else {
      fileGroups.set(info.filePath, [info]);
      fileOrder.push(info.filePath);
    }
  }

  // 3. Build chips from groups
  const chips: Array<ChipData> = [];

  // Compute display names for all files
  const displayNames = disambiguateFileNames(fileOrder);

  for (const filePath of fileOrder) {
    const infos = fileGroups.get(filePath)!;
    const displayName = displayNames.get(filePath) ?? filePath;
    const isNewFile = infos.every((info) => info.block.name === "Write");

    // Check if any block is still executing
    const hasExecuting = infos.some((info) => info.state === "executing");

    if (hasExecuting) {
      // Optimistic merge: all blocks in one executing chip.
      // Show partial stats from already-completed blocks so the user can see
      // progress while the remaining blocks are still running.
      const completedInfos = infos.filter((i) => i.state === "completed");
      let stats: { added: number; removed: number } | null = null;
      if (completedInfos.length > 0) {
        let added = 0;
        let removed = 0;
        for (const info of completedInfos) {
          if (info.result && isDiffToolContent(info.result.content)) {
            const counts = getLineCounts(info.result.content.diff);
            added += counts.added;
            removed += counts.removed;
          }
        }

        if (added > 0 || removed > 0) {
          stats = { added, removed };
        }
      }
      chips.push({
        id: infos[0].block.id,
        filePath,
        displayName,
        state: "executing",
        stats,
        isNewFile,
        blocks: infos.map((i) => i.block),
        results: infos.filter((i) => i.result !== undefined).map((i) => i.result!),
        errorDetail: null,
        errorContentType: null,
      });
      continue;
    }

    // All terminal — check if states are uniform
    const states = new Set(infos.map((i) => i.state));

    if (states.size === 1) {
      // All same state — merge
      const state = infos[0].state;
      chips.push(buildSingleChip(infos, filePath, displayName, state, isNewFile));
    } else {
      // Mixed states — split by state
      const byState = new Map<ChipState, Array<BlockInfo>>();
      for (const info of infos) {
        const group = byState.get(info.state);
        if (group) {
          group.push(info);
        } else {
          byState.set(info.state, [info]);
        }
      }

      for (const [state, stateInfos] of byState) {
        chips.push(buildSingleChip(stateInfos, filePath, displayName, state, isNewFile));
      }
    }
  }

  return chips;
};

const getToolName = (block: ToolUseBlock | ToolResultBlock): string =>
  block.type === "tool_use" ? block.name : (block as ToolResultBlock).toolName;

/**
 * Convert a ToolResultBlock for a diff tool into a ToolUseBlock shim.
 *
 * The backend replaces ToolUseBlocks with their ToolResultBlocks in completed
 * messages. The chip system expects ToolUseBlocks keyed by the tool-use ID so
 * that it can look up the result via toolResultMap.  This shim bridges the gap.
 */
const resultToToolUseShim = (result: ToolResultBlock): ToolUseBlock => ({
  type: "tool_use",
  objectType: "ToolUseBlock",
  id: result.toolUseId,
  name: result.toolName,
  input: {},
  invocationString: result.invocationString,
});

/**
 * Partition an ordered array of tool blocks into alternating chip-row
 * and tool-group segments. Chip segments contain ToolUseBlocks (or shims
 * derived from ToolResultBlocks) for diff tools; everything else goes
 * into tool segments.
 */
export const segmentToolBlocks = (blocks: ReadonlyArray<ToolUseBlock | ToolResultBlock>): ReadonlyArray<Segment> => {
  const segments: Array<Segment> = [];
  let currentChipBlocks: Array<ToolUseBlock> = [];
  let currentToolBlocks: Array<ToolUseBlock | ToolResultBlock> = [];

  const flushChip = (): void => {
    if (currentChipBlocks.length > 0) {
      segments.push({ kind: "chip", blocks: currentChipBlocks });
      currentChipBlocks = [];
    }
  };

  const flushTools = (): void => {
    if (currentToolBlocks.length > 0) {
      segments.push({ kind: "tools", blocks: currentToolBlocks });
      currentToolBlocks = [];
    }
  };

  for (const block of blocks) {
    const name = getToolName(block);

    if (isDiffTool(name)) {
      // Diff tools normally render as file chips, but a chip requires a
      // derivable file path — without one buildChipData would silently drop the
      // block, making the tool call vanish. Fall back to a tool pill so the
      // call still appears (e.g. an Edit to a file outside the workspace whose
      // result carries no path).
      if (block.type === "tool_use" && getFilePathFromToolBlock(block) !== null) {
        flushTools();
        currentChipBlocks.push(block);
        continue;
      }

      if (block.type === "tool_result") {
        // The backend replaces tool_use with tool_result in completed messages.
        // Convert back to a ToolUseBlock shim so the chip row can render it.
        const result = block as ToolResultBlock;
        const shim = resultToToolUseShim(result);
        if (getFilePathFromToolBlock(shim, result) !== null) {
          flushTools();
          currentChipBlocks.push(shim);
          continue;
        }
      }
      // No derivable file path — fall through to the tool pill segment below.
    }

    // Everything else (including Bash and path-less diff tools) goes into a
    // tool pill segment.
    flushChip();
    currentToolBlocks.push(block);
  }

  flushChip();
  flushTools();

  return segments;
};

const buildSingleChip = (
  infos: Array<BlockInfo>,
  filePath: string,
  displayName: string,
  state: ChipState,
  isNewFile: boolean,
): ChipData => {
  let stats: { added: number; removed: number } | null = null;
  let errorDetail: string | null = null;
  let errorContentType: "diff" | "text" | null = null;

  if (state === "completed") {
    let added = 0;
    let removed = 0;
    for (const info of infos) {
      if (info.result && isDiffToolContent(info.result.content)) {
        const counts = getLineCounts(info.result.content.diff);
        added += counts.added;
        removed += counts.removed;
      }
    }
    stats = { added, removed };
  } else if (state === "error") {
    const firstError = infos.find((i) => i.result?.isError);
    if (firstError?.result) {
      const content = firstError.result.content;
      if (isGenericToolContent(content)) {
        errorDetail = content.text;
        errorContentType = "text";
      } else if (isDiffToolContent(content)) {
        errorDetail = content.diff;
        errorContentType = "diff";
      }
    }
  }

  return {
    id: infos[0].block.id,
    filePath,
    displayName,
    state,
    stats,
    isNewFile,
    blocks: infos.map((i) => i.block),
    results: infos.filter((i) => i.result !== undefined).map((i) => i.result!),
    errorDetail,
    errorContentType,
  };
};
