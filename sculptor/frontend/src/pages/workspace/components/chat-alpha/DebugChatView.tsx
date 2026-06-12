import { type ReactElement, useState } from "react";

import type { ChatMessage } from "~/api";
import { ElementIds } from "~/api";

import styles from "./DebugChatView.module.scss";
import { getPlainText, getToolResultSummary, getToolUseSummary } from "./messageUtils.ts";
import { formatTimestamp, getPromptCycleBaselines, type TimestampFormat } from "./timestampUtils.ts";

type DebugChatViewProps = {
  messages: ReadonlyArray<ChatMessage>;
};

export const DebugChatView = ({ messages }: DebugChatViewProps): ReactElement => {
  const [timestampFormat, setTimestampFormat] = useState<TimestampFormat>("relative");

  const toggleTimestampFormat = (): void => {
    setTimestampFormat((prev) => (prev === "relative" ? "absolute" : "relative"));
  };

  const promptCycleBaselines = getPromptCycleBaselines(messages);

  return (
    <div className={styles.scrollArea} data-testid={ElementIds.DEBUG_CHAT_VIEW}>
      <div className={styles.container}>
        {messages.length === 0 && <p className={styles.empty}>No messages yet</p>}
        {messages.map((message, index) => {
          const text = getPlainText(message);
          const toolUses = getToolUseSummary(message);
          const toolResults = getToolResultSummary(message);
          const blockTypes = message.content.map((b) => b.type ?? "unknown").join(", ");
          const formattedTimestamp = formatTimestamp(
            message.approximateCreationTime,
            promptCycleBaselines[index],
            timestampFormat,
          );

          return (
            <div
              key={`${message.id}-${index}`}
              className={styles.messageBlock}
              data-testid={ElementIds.DEBUG_CHAT_BLOCK}
            >
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>role</span>
                <span className={styles.metaValue}>{message.role}</span>
                <span className={styles.metaLabel}>id</span>
                <span className={styles.metaValue}>{message.id}</span>
                <span className={styles.metaLabel}>blocks</span>
                <span className={styles.metaValue}>[{blockTypes}]</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>timestamp</span>
                <span className={`${styles.metaValue} ${styles.timestamp}`} onClick={toggleTimestampFormat}>
                  {formattedTimestamp}
                </span>
              </div>
              {message.parentToolUseId && (
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>parentToolUseId</span>
                  <span className={styles.metaValue}>{message.parentToolUseId}</span>
                </div>
              )}
              {toolUses.length > 0 && (
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>tool_use</span>
                  <span className={styles.metaValue}>{toolUses.join(", ")}</span>
                </div>
              )}
              {toolResults.length > 0 && (
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>tool_result</span>
                  <span className={styles.metaValue}>{toolResults.join(", ")}</span>
                </div>
              )}
              {text && <p className={styles.messageText}>{text}</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
};
