import type { ReactElement } from "react";
import { useMemo } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/chat/utils/subagentTree.ts";

import { ChatMarkdownBlock } from "./ChatMarkdownBlock.tsx";
import { collectLeafToolBlocks } from "./subagentBlockUtils.ts";
import styles from "./SubagentPopover.module.scss";
import { ToolNavigationProvider } from "./ToolNavigationContext.tsx";
import { ToolPillRow } from "./ToolPillRow.tsx";

const formatSubagentType = (subagentType: string | undefined): string => {
  if (!subagentType) return "Subagent";
  return subagentType.charAt(0).toUpperCase() + subagentType.slice(1) + " subagent";
};

type SubagentPopoverProps = {
  parentBlock: ToolUseBlock;
  childNodes: Array<SubagentTreeNode>;
  toolResultMap: Map<string, ToolResultBlock>;
  metadata?: SubagentMetadata;
  isThinking: boolean;
};

export const SubagentPopover = ({
  parentBlock,
  childNodes,
  toolResultMap,
  metadata,
  isThinking,
}: SubagentPopoverProps): ReactElement => {
  const typeLabel = formatSubagentType(metadata?.subagentType);

  const leafBlocks = useMemo(() => collectLeafToolBlocks(childNodes), [childNodes]);

  return (
    <div className={styles.popover}>
      <div className={styles.body}>
        {metadata?.prompt && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>{typeLabel} prompt</div>
            <div className={styles.prompt}>
              <ChatMarkdownBlock content={metadata.prompt} />
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
                <ToolPillRow
                  blocks={leafBlocks}
                  toolResultMap={toolResultMap}
                  inProgressMessageId={isThinking ? parentBlock.id : null}
                />
              </ToolNavigationProvider>
            </div>
          </div>
        )}

        {metadata?.responseText && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Response</div>
            <div className={styles.response}>
              <ChatMarkdownBlock content={metadata.responseText} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
