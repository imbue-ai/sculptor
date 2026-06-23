import type { ReactElement } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";

import { AlphaChipRow } from "./AlphaChipRow.tsx";
import { AlphaToolPillRow } from "./AlphaToolPillRow.tsx";
import { segmentToolBlocks } from "./chipRowUtils.ts";

/**
 * Render an ordered array of tool blocks as alternating chip rows
 * (for diff tools) and pill rows (for everything else, including Bash).
 *
 * Callers are responsible for wrapping the result in a `ToolNavigationProvider`
 * if they want arrow-key navigation across rows, and for supplying a
 * `rowIndexOffset` when rendering alongside other navigable rows in the same
 * provider (e.g. subagent pills above the tool segments).
 */
export const renderToolSegments = (
  blocks: ReadonlyArray<ToolUseBlock | ToolResultBlock>,
  toolResultMap: Map<string, ToolResultBlock>,
  opts: { isActive: boolean; inProgressMessageId: string | null; rowIndexOffset?: number },
): ReactElement => {
  const segments = segmentToolBlocks(blocks);
  const offset = opts.rowIndexOffset ?? 0;

  return (
    <>
      {segments.map((segment, index) => {
        // Derive a stable key from the first block in the segment
        const firstBlock = segment.blocks[0];
        const blockId = firstBlock.type === "tool_use" ? firstBlock.id : (firstBlock as ToolResultBlock).toolUseId;
        const key = `${segment.kind}-${blockId}`;

        if (segment.kind === "chip") {
          return (
            <AlphaChipRow
              key={key}
              rowIndex={offset + index}
              blocks={segment.blocks}
              toolResultMap={toolResultMap}
              inProgressMessageId={opts.inProgressMessageId}
            />
          );
        }

        return (
          <AlphaToolPillRow
            key={key}
            rowIndex={offset + index}
            blocks={segment.blocks}
            toolResultMap={toolResultMap}
            inProgressMessageId={opts.inProgressMessageId}
          />
        );
      })}
    </>
  );
};
