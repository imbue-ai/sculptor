import type { ReactElement } from "react";

import type { ToolResultBlock } from "~/api";
import { ChatMessageRole, ElementIds, TaskStatus } from "~/api";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/chat/utils/subagentTree.ts";

import { AssistantMessageContent } from "./AssistantMessage.tsx";
import styles from "./ChatView.module.scss";
import { StreamingCursor } from "./StreamingCursor.tsx";
import { TurnFooter } from "./TurnFooter.tsx";
import { UserMessageContent as UserMessage } from "./UserMessage.tsx";
import { useTurnSummaryData } from "./useTurnSummaryData.ts";

const EMPTY_SUBAGENT_MAP = new Map<string, SubagentMetadata>();

/**
 * Message node used by the virtualized ChatInterface.
 * Renders a single message with optional search highlighting.
 */
type MessageNodeProps = {
  node: SubagentTreeNode;
  prevNode: SubagentTreeNode | undefined;
  inProgressMessageId: string | null;
  toolResultMap: Map<string, ToolResultBlock>;
  subagentMetadataMap?: Map<string, SubagentMetadata>;
  searchQuery?: string;
  /** The content block index (in message.content) that contains the active search match. -1 for none. */
  activeSearchBlockIndex?: number;
  /** The occurrence index within the active block. -1 for none. */
  activeSearchOccurrence?: number;
  isLastMessage?: boolean;
  isStreaming?: boolean;
  agentStatus?: TaskStatus;
  onRetryRequest?: () => void;
  onOpenDiffFile?: (filePath: string) => void;
  messageIndex?: number;
};

export const MessageNode = ({
  node,
  prevNode,
  inProgressMessageId,
  toolResultMap,
  subagentMetadataMap,
  searchQuery,
  activeSearchBlockIndex = -1,
  activeSearchOccurrence = -1,
  isLastMessage = false,
  isStreaming = false,
  agentStatus = TaskStatus.RUNNING,
  onRetryRequest,
  onOpenDiffFile,
  messageIndex = 0,
}: MessageNodeProps): ReactElement => {
  const message = node.message;
  const turnSummaryData = useTurnSummaryData(node);
  const isUser = message.role === ChatMessageRole.USER;
  const isNewCycle = isUser && (prevNode === undefined || prevNode.message.role === ChatMessageRole.ASSISTANT);
  const isAfterUser = !isUser && prevNode !== undefined && prevNode.message.role === ChatMessageRole.USER;
  const isAfterAssistant = !isUser && prevNode !== undefined && prevNode.message.role === ChatMessageRole.ASSISTANT;

  const messageClass = [
    styles.message,
    isNewCycle && styles.newCycle,
    isAfterUser && styles.afterUser,
    isAfterAssistant && styles.afterAssistant,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={messageClass} data-testid={ElementIds.ALPHA_CHAT_MESSAGE} data-role={isUser ? "user" : "assistant"}>
      {isUser ? (
        <>
          <div className={styles.userBubble}>
            <UserMessage
              message={message}
              approximateCreationTime={message.approximateCreationTime}
              searchQuery={searchQuery}
              activeSearchBlockIndex={activeSearchBlockIndex}
              activeSearchOccurrence={activeSearchOccurrence}
              messageIndex={messageIndex}
            />
          </div>
          {isLastMessage && agentStatus === TaskStatus.RUNNING && <StreamingCursor />}
        </>
      ) : (
        <AssistantMessageContent
          message={message}
          node={node}
          toolResultMap={toolResultMap}
          subagentMetadataMap={subagentMetadataMap ?? EMPTY_SUBAGENT_MAP}
          inProgressMessageId={inProgressMessageId}
          isLastMessage={isLastMessage}
          isStreaming={isStreaming}
          agentStatus={agentStatus}
          onRetryRequest={onRetryRequest}
          searchQuery={searchQuery}
          activeSearchBlockIndex={activeSearchBlockIndex}
          activeSearchOccurrence={activeSearchOccurrence}
          messageIndex={messageIndex}
        />
      )}

      {!isUser && (message.turnMetrics || message.stopped) && (
        <TurnFooter
          metrics={message.turnMetrics}
          stopped={message.stopped}
          files={turnSummaryData}
          onFileClick={onOpenDiffFile}
        />
      )}
    </div>
  );
};
