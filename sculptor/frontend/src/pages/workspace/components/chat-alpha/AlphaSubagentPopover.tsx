import type { ReactElement } from "react";
import { useMemo } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
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

  // A background agent's tool calls stop streaming into the parent transcript
  // once it moves to the background: only calls made before that point (if
  // any) appear under Tools, so tell the user the list is incomplete.
  const isBackground = metadata?.isBackground === true;
  const backgroundToolsNote =
    leafBlocks.length > 0
      ? "Only tool calls from before the agent moved to the background are shown."
      : "This agent's tool calls run in the background and aren't shown here.";

  return (
    <div className={styles.popover}>
      <div className={styles.body}>
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
        {(leafBlocks.length > 0 || isBackground) && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Tools</div>
            {leafBlocks.length > 0 && (
              <div className={styles.pillsArea}>
                <ToolNavigationProvider>
                  <AlphaToolPillRow
                    blocks={leafBlocks}
                    toolResultMap={toolResultMap}
                    inProgressMessageId={isThinking ? parentBlock.id : null}
                  />
                </ToolNavigationProvider>
              </div>
            )}
            {isBackground && (
              <div className={styles.backgroundNote} data-testid={ElementIds.ALPHA_CHAT_SUBAGENT_POPOVER_NOTE}>
                {backgroundToolsNote}
              </div>
            )}
          </div>
        )}

        {metadata?.responseText ? (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Response</div>
            <div className={styles.response} data-testid={ElementIds.ALPHA_CHAT_SUBAGENT_POPOVER_RESPONSE}>
              <AlphaMarkdownBlock content={metadata.responseText} />
            </div>
          </div>
        ) : (
          isBackground && (
            <div className={styles.section}>
              <div className={styles.sectionLabel}>Response</div>
              <div className={styles.backgroundStatus} data-testid={ElementIds.ALPHA_CHAT_SUBAGENT_POPOVER_STATUS}>
                {isThinking
                  ? "Running in the background — the response will appear here when the agent finishes."
                  : "The agent finished in the background, but its response wasn't captured."}
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
};
