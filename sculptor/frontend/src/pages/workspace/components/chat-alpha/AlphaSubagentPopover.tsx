import type { ReactElement } from "react";
import { useMemo } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";
import { formatSubagentType } from "~/pages/workspace/utils/utils.ts";

import { AlphaMarkdownBlock } from "./AlphaMarkdownBlock.tsx";
import styles from "./AlphaSubagentPopover.module.scss";
import { AlphaToolPillRow } from "./AlphaToolPillRow.tsx";
import { collectLeafToolBlocks } from "./subagentBlockUtils.ts";
import { ToolNavigationProvider } from "./ToolNavigationContext.tsx";

type AlphaSubagentPopoverProps = {
  parentBlock: ToolUseBlock;
  childNodes: Array<SubagentTreeNode>;
  toolResultMap: Map<string, ToolResultBlock>;
  metadata?: SubagentMetadata;
  isThinking: boolean;
};

export const AlphaSubagentPopover = ({
  parentBlock,
  childNodes,
  toolResultMap,
  metadata,
  isThinking,
}: AlphaSubagentPopoverProps): ReactElement => {
  const typeLabel = formatSubagentType(metadata?.subagentType);

  const leafBlocks = useMemo(() => collectLeafToolBlocks(childNodes), [childNodes]);

  return (
    <div className={styles.popover}>
      {/* Body: scrollable */}
      <div className={styles.body}>
        {/* Prompt */}
        {metadata?.prompt && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>{typeLabel} prompt</div>
            <div className={styles.prompt}>
              <AlphaMarkdownBlock content={metadata.prompt} />
            </div>
          </div>
        )}

        {/* Nested tool pills.
            Wrap in our own ToolNavigationProvider so the inner pills don't
            share the parent provider's `openItemId` with the subagent pill —
            otherwise opening any inner pill would set openItemId to that
            pill's id, which flips the subagent pill's `isOpen` to false and
            collapses the surrounding popover. */}
        {leafBlocks.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Tools</div>
            <div className={styles.pillsArea}>
              <ToolNavigationProvider>
                <AlphaToolPillRow
                  blocks={leafBlocks}
                  toolResultMap={toolResultMap}
                  inProgressMessageId={isThinking ? parentBlock.id : null}
                />
              </ToolNavigationProvider>
            </div>
          </div>
        )}

        {/* Response */}
        {metadata?.responseText && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Response</div>
            <div className={styles.response}>
              <AlphaMarkdownBlock content={metadata.responseText} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
