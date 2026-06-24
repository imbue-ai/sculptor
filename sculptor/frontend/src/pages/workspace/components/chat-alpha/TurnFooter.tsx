import { Flex, Popover, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useState } from "react";

import type { TurnMetrics } from "~/api";
import { ElementIds } from "~/api";

import { TokenPopoverContent } from "./TokenPopoverContent.tsx";
import styles from "./TurnFooter.module.scss";
import type { TurnFile } from "./useTurnSummaryData";

const numberFormat = new Intl.NumberFormat("en-US");

const FilePath = ({ path }: { path: string }): ReactElement => {
  const parts = path.split("/");
  const dirParts = parts.slice(0, -1);
  const fileName = parts[parts.length - 1];

  return (
    <span className={styles.filePath}>
      {dirParts.length > 0 && (
        <>
          <span className={styles.dirPath}>
            {dirParts.map((part, index) => (
              <span key={index}>
                {index > 0 && <span className={styles.separator}>/</span>}
                {part}
              </span>
            ))}
          </span>
          <span className={styles.separator}>/</span>
        </>
      )}
      <span className={styles.fileName}>{fileName}</span>
    </span>
  );
};

const FileChangesPopover = ({
  files,
  onFileClick,
}: {
  files: ReadonlyArray<TurnFile>;
  onFileClick?: (filePath: string) => void;
}): ReactElement => {
  const [isOpen, setIsOpen] = useState<boolean>(false);

  return (
    <Popover.Root open={isOpen} onOpenChange={setIsOpen}>
      <Popover.Trigger>
        <span className={styles.diffStats} data-testid={ElementIds.TURN_FOOTER_FILE_COUNT}>
          {files.length} {files.length === 1 ? "file" : "files"} changed
        </span>
      </Popover.Trigger>
      <Popover.Content
        side="top"
        align="start"
        size="1"
        className={styles.popover}
        onFocusOutside={(e): void => e.preventDefault()}
      >
        {files.map((file) => (
          <Flex
            key={file.path}
            align="center"
            justify="end"
            className={styles.popoverFileRow}
            data-testid={ElementIds.TURN_FOOTER_FILE_ROW}
            onClick={(): void => onFileClick?.(file.path)}
            onKeyDown={(e): void => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onFileClick?.(file.path);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <Text size="1" className={styles.fileRowText}>
              <FilePath path={file.path} />
            </Text>
          </Flex>
        ))}
      </Popover.Content>
    </Popover.Root>
  );
};

type TurnFooterProps = {
  metrics?: TurnMetrics | null;
  stopped?: boolean;
  files?: ReadonlyArray<TurnFile>;
  onFileClick?: (filePath: string) => void;
};

export const TurnFooter = ({ metrics, stopped, files, onFileClick }: TurnFooterProps): ReactElement => {
  const duration = metrics ? `${metrics.durationSeconds.toFixed(1)}s` : null;
  const inputTokens = metrics?.inputTokens;
  const outputTokens = metrics?.outputTokens;
  const totalTokens =
    inputTokens != null && outputTokens != null ? inputTokens + outputTokens + (metrics?.reasoningTokens ?? 0) : null;
  const tokens = totalTokens !== null ? `${numberFormat.format(totalTokens)} tokens` : null;

  const contextTokens = metrics?.contextTotalTokens;
  const contextThreshold = metrics?.autoCompactThreshold;
  const hasContext = contextTokens != null && contextTokens > 0 && contextThreshold != null && contextThreshold > 0;
  const contextPercent =
    hasContext && contextTokens != null && contextThreshold != null
      ? Math.min(100, Math.round((contextTokens / contextThreshold) * 100))
      : null;

  const hasFiles = files != null && files.length > 0;

  return (
    <div className={styles.footer} data-testid={ElementIds.TURN_FOOTER}>
      {stopped && <span className={styles.stoppedLabel}>Stopped</span>}
      {stopped && duration && " \u00B7 "}
      {duration}
      {duration && tokens && " \u00B7 "}
      {tokens && metrics && (
        <Popover.Root>
          <Popover.Trigger>
            <span className={styles.tokenCount} data-testid={ElementIds.TURN_FOOTER_TOKEN_COUNT}>
              {tokens}
            </span>
          </Popover.Trigger>
          <Popover.Content side="top" align="start" size="1" className={styles.popover}>
            <TokenPopoverContent turnMetrics={metrics} />
          </Popover.Content>
        </Popover.Root>
      )}
      {hasContext && contextPercent !== null && (
        <>
          {(duration || tokens) && " \u00B7 "}
          <Popover.Root>
            <Popover.Trigger>
              <span className={styles.tokenCount}>{contextPercent}% context</span>
            </Popover.Trigger>
            <Popover.Content side="top" align="start" size="1" className={styles.popover}>
              <TokenPopoverContent turnContextTokens={contextTokens} autoCompactThreshold={contextThreshold} />
            </Popover.Content>
          </Popover.Root>
        </>
      )}
      {hasFiles && (
        <>
          {(duration || tokens || hasContext) && " \u00B7 "}
          <FileChangesPopover files={files} onFileClick={onFileClick} />
        </>
      )}
    </div>
  );
};
