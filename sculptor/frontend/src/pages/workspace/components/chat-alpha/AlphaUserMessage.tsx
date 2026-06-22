import { IconButton, Text, Tooltip } from "@radix-ui/themes";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage, FileBlock } from "~/api";
import { ElementIds } from "~/api";
import type { BlockUnion } from "~/common/Guards";
import { isFileBlock, isTextBlock } from "~/common/Guards";
import { FilePreviewList } from "~/components/FilePreviewList.tsx";
import { stripHtml } from "~/pages/workspace/utils/utils.ts";

import styles from "./AlphaChatView.module.scss";
import { AlphaMarkdownBlock } from "./AlphaMarkdownBlock.tsx";
import { formatHumanTimestamp } from "./timestampUtils.ts";

export const UserMessageContent = ({
  message,
  approximateCreationTime,
  searchQuery,
  activeSearchBlockIndex = -1,
  activeSearchOccurrence = -1,
  messageIndex = 0,
}: {
  message: ChatMessage;
  approximateCreationTime: string;
  searchQuery?: string;
  activeSearchBlockIndex?: number;
  activeSearchOccurrence?: number;
  messageIndex?: number;
}): ReactElement => {
  const [isCopied, setIsCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const textBlocks = useMemo(
    () => message.content.filter((block: BlockUnion) => isTextBlock(block)),
    [message.content],
  );
  const fileBlocks = useMemo(
    () => message.content.filter((block: BlockUnion): block is FileBlock => isFileBlock(block)),
    [message.content],
  );

  useEffect(() => {
    return (): void => clearTimeout(copyTimerRef.current);
  }, []);

  const handleCopy = useCallback((): void => {
    const content = textBlocks.map((block) => stripHtml((block as { text: string }).text)).join("");
    navigator.clipboard.writeText(content);
    setIsCopied(true);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setIsCopied(false), 1500);
  }, [textBlocks]);

  return (
    <div>
      {message.sentVia && (
        <Text size="1" color="gray" data-testid={ElementIds.SCULPT_SENT_VIA_BADGE} className={styles.sentViaBadge}>
          via {message.sentVia}
        </Text>
      )}
      {textBlocks.map((block, index) => {
        const textBlock = block as { text: string };
        return (
          <div key={index} data-testid={ElementIds.ALPHA_CHAT_TEXT}>
            <AlphaMarkdownBlock
              content={textBlock.text}
              enableFileLinks={false}
              searchQuery={searchQuery}
              activeOccurrenceIndex={index === activeSearchBlockIndex ? activeSearchOccurrence : -1}
            />
          </div>
        );
      })}
      {fileBlocks.length > 0 && (
        <FilePreviewList
          files={fileBlocks.map((b) => b.source)}
          displayMode="inline"
          listId={`${messageIndex}-user`}
          listOrder={messageIndex * 1000 + 999}
        />
      )}
      <div className={styles.userBubbleFooter}>
        <time className={styles.userTimestamp} dateTime={approximateCreationTime}>
          {formatHumanTimestamp(approximateCreationTime)}
        </time>
        {textBlocks.length > 0 && (
          <Tooltip content="Copy message">
            <IconButton
              variant="ghost"
              size="1"
              className={styles.copyButton}
              onClick={handleCopy}
              aria-label="Copy message"
              data-testid={ElementIds.ALPHA_CHAT_COPY_BUTTON}
            >
              {isCopied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
            </IconButton>
          </Tooltip>
        )}
      </div>
    </div>
  );
};
