import type { ReactElement } from "react";
import { useMemo } from "react";

import type { ChatMessage, ToolResultBlock } from "~/api";
import { ElementIds, TaskStatus } from "~/api";
import type { SubagentMetadata } from "~/pages/workspace/chatAlpha/utils/subagentTree.ts";
import type { SubagentTreeNode } from "~/pages/workspace/chatAlpha/utils/subagentTree.ts";
import { FilePreviewList } from "~/pages/workspace/filePreview/FilePreviewList.tsx";

import styles from "./AlphaChatView.module.scss";
import { AlphaContextSummary } from "./AlphaContextSummary.tsx";
import { AlphaErrorBlock } from "./AlphaErrorBlock.tsx";
import { AlphaMarkdownBlock } from "./AlphaMarkdownBlock.tsx";
import { ToolBlockGroup } from "./AlphaToolGroup.tsx";
import { AlphaWarningBlock } from "./AlphaWarningBlock.tsx";
import { buildRenderGroups } from "./buildRenderGroups.ts";
import { MESSAGE_LIST_ORDER_STRIDE } from "./messageUtils.ts";
import { StreamingCursor } from "./StreamingCursor.tsx";

export const AssistantMessageContent = ({
  message,
  node,
  toolResultMap,
  subagentMetadataMap,
  inProgressMessageId,
  isLastMessage,
  isStreaming,
  taskStatus,
  onRetryRequest,
  searchQuery,
  activeSearchBlockIndex = -1,
  activeSearchOccurrence = -1,
  messageIndex = 0,
}: {
  message: ChatMessage;
  node: SubagentTreeNode;
  toolResultMap: Map<string, ToolResultBlock>;
  subagentMetadataMap: Map<string, SubagentMetadata>;
  inProgressMessageId?: string | null;
  isLastMessage: boolean;
  isStreaming: boolean;
  taskStatus: TaskStatus;
  onRetryRequest?: () => void;
  searchQuery?: string;
  activeSearchBlockIndex?: number;
  activeSearchOccurrence?: number;
  messageIndex?: number;
}): ReactElement => {
  const groups = useMemo(() => buildRenderGroups(message.content, node.children), [message.content, node.children]);

  const isTurnActive = isLastMessage && taskStatus === TaskStatus.RUNNING;
  const lastGroupType = groups.length > 0 ? groups[groups.length - 1].type : null;

  return (
    <>
      {groups.map((group, groupIndex) => {
        const isLastGroup = groupIndex === groups.length - 1;

        if (group.type === "text") {
          const merged = group.blocks.map((b) => b.text).join("");
          const hasCursor = isTurnActive && isLastGroup;
          return (
            <div key={`text-${groupIndex}`} data-testid={ElementIds.ALPHA_CHAT_TEXT}>
              <AlphaMarkdownBlock
                content={merged}
                searchQuery={searchQuery}
                activeOccurrenceIndex={groupIndex === activeSearchBlockIndex ? activeSearchOccurrence : -1}
                showCursor={hasCursor}
              />
            </div>
          );
        }

        if (group.type === "tools") {
          return (
            <ToolBlockGroup
              key={`tools-${groupIndex}`}
              blocks={group.blocks}
              node={node}
              toolResultMap={toolResultMap}
              subagentMetadataMap={subagentMetadataMap}
              inProgressMessageId={inProgressMessageId}
              isActive={isStreaming && isLastGroup}
            />
          );
        }

        if (group.type === "error") {
          return (
            <AlphaErrorBlock
              key={`error-${groupIndex}`}
              block={group.block}
              isLastMessage={isLastMessage && isLastGroup}
              taskStatus={taskStatus}
              onRetryRequest={onRetryRequest}
            />
          );
        }

        if (group.type === "warning") {
          return <AlphaWarningBlock key={`warning-${groupIndex}`} block={group.block} />;
        }

        if (group.type === "context_summary") {
          return <AlphaContextSummary key={`ctx-${groupIndex}`} text={group.text} label="Context Compacted" />;
        }

        if (group.type === "context_cleared") {
          return <AlphaContextSummary key={`ctx-${groupIndex}`} text={group.text} label="Context Cleared" />;
        }

        if (group.type === "resume_response") {
          return (
            <div
              key={`resume-${groupIndex}`}
              data-testid={ElementIds.RESUME_RESPONSE}
              className={styles.resumeIndicator}
            >
              Resumed agent response
            </div>
          );
        }

        if (group.type === "files") {
          return (
            <FilePreviewList
              key={`files-${groupIndex}`}
              files={group.blocks.map((b) => b.source)}
              displayMode="inline"
              allowCopyImage
              listId={`${messageIndex}-files-${groupIndex}`}
              listOrder={messageIndex * MESSAGE_LIST_ORDER_STRIDE + groupIndex}
            />
          );
        }

        return null;
      })}
      {isTurnActive && lastGroupType !== "text" && <StreamingCursor />}
    </>
  );
};
