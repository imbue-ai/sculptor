import { IconButton } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { ChevronRightIcon, PanelRightOpenIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import type { DiffToolContent, GenericToolContent, ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import { isDiffToolContent, isGenericToolContent } from "~/common/Guards";
import { appThemeAtom } from "~/common/state/atoms/userConfig";
import { parseDiff } from "~/components/DiffUtils";
import { LargeDiffGate } from "~/pages/workspace/components/diffPanel/LargeDiffGate";
import { PierreDiffView } from "~/pages/workspace/components/diffPanel/PierreDiffView";

import styles from "./AlphaChatView.module.scss";
import { PulsingDot } from "./pill-animations";

const getToolResultText = (content: GenericToolContent | DiffToolContent): string => {
  if (isGenericToolContent(content)) return content.text;
  if (isDiffToolContent(content)) return content.diff;
  return "";
};

const formatToolInput = (input: Record<string, unknown>): string => {
  const entries = Object.entries(input);
  if (entries.length === 0) return "";
  if (entries.length === 1) {
    const [, value] = entries[0];
    if (typeof value === "string") return value;
  }
  const firstString = entries.find(([, v]) => typeof v === "string");
  if (firstString) return firstString[1] as string;
  return "";
};

const DiffResult = ({ content }: { content: DiffToolContent }): ReactElement => {
  const diffData = useMemo(() => parseDiff(content.diff), [content.diff]);
  const themeType = useAtomValue(appThemeAtom);

  return (
    <div className={styles.diffResultContainer} onClick={(e): void => e.stopPropagation()} role="presentation">
      {diffData.diffStrings.map((diffString: string, i: number) => (
        <LargeDiffGate key={i} diffString={diffString}>
          {(visibleDiff): ReactElement => (
            <PierreDiffView
              diffString={visibleDiff}
              viewType="unified"
              overflow="wrap"
              themeType={themeType}
              hideHandle={true}
            />
          )}
        </LargeDiffGate>
      ))}
    </div>
  );
};

const DiffPanelButton = ({
  filePath,
  onOpenDiffPanel,
}: {
  filePath: string;
  onOpenDiffPanel?: (filePath: string) => void;
}): ReactElement | null => {
  const handleClick = useCallback(
    (e: React.MouseEvent): void => {
      e.stopPropagation();
      onOpenDiffPanel?.(filePath);
    },
    [filePath, onOpenDiffPanel],
  );

  if (!onOpenDiffPanel) return null;

  return (
    <IconButton
      size="1"
      variant="ghost"
      color="gray"
      className={styles.diffPanelButton}
      onClick={handleClick}
      aria-label={`Open ${filePath} in diff panel`}
    >
      <PanelRightOpenIcon size={12} />
    </IconButton>
  );
};

const getToolLineClassName = ({
  isExecuting,
  isOpen,
  isError,
}: {
  isExecuting?: boolean;
  isOpen: boolean;
  isError?: boolean;
}): string => {
  if (isError) return `${styles.toolLine} ${styles.errorToolLine}`;
  if (isExecuting) return `${styles.toolLine} ${styles.executingToolLine}`;
  if (isOpen) return `${styles.toolLine} ${styles.expandedToolLine}`;
  return styles.toolLine;
};

export const ToolLine = ({
  block,
  result,
  isExecuting,
  onOpenDiffPanel,
}: {
  block: ToolUseBlock;
  result: ToolResultBlock | undefined;
  isExecuting?: boolean;
  onOpenDiffPanel?: (filePath: string) => void;
}): ReactElement => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const inputSummary = block.input && Object.keys(block.input).length > 0 ? formatToolInput(block.input) : undefined;

  const isError = result?.isError ?? false;
  const hasDiffResult = result && isDiffToolContent(result.content) && !isError;
  const resultText = result && !hasDiffResult ? getToolResultText(result.content) : undefined;
  const errorClass = isError ? ` ${styles.toolResultError}` : "";
  const diffFilePath = result && isDiffToolContent(result.content) ? result.content.filePath : undefined;

  return (
    <div
      className={getToolLineClassName({ isExecuting, isOpen, isError })}
      onClick={(): void => setIsOpen((prev) => !prev)}
      role="button"
      tabIndex={0}
      aria-expanded={isOpen}
      data-testid={ElementIds.ALPHA_CHAT_TOOL_LINE}
      onKeyDown={(e): void => {
        if (e.key === "Enter" || e.key === " ") setIsOpen((prev) => !prev);
      }}
    >
      <div className={styles.toolHeader}>
        {isExecuting ? (
          <PulsingDot />
        ) : (
          <ChevronRightIcon size={12} className={isOpen ? styles.chevronOpen : styles.chevronClosed} />
        )}
        <span className={styles.toolName} data-testid={ElementIds.ALPHA_CHAT_TOOL_NAME}>
          {block.name}
        </span>
        {inputSummary && <span className={styles.toolInput}>{inputSummary}</span>}
        {diffFilePath && <DiffPanelButton filePath={diffFilePath} onOpenDiffPanel={onOpenDiffPanel} />}
      </div>
      {isOpen && hasDiffResult && <DiffResult content={result.content as DiffToolContent} />}
      {isOpen && resultText && <pre className={`${styles.toolResult}${errorClass}`}>{resultText}</pre>}
    </div>
  );
};

export const CompletedToolLine = ({
  block,
  onOpenDiffPanel,
}: {
  block: ToolResultBlock;
  onOpenDiffPanel?: (filePath: string) => void;
}): ReactElement => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const invocationSummary = block.invocationString ?? block.toolName ?? "tool";

  const isError = block.isError ?? false;
  const hasDiffResult = isDiffToolContent(block.content) && !isError;
  const resultText = !hasDiffResult ? getToolResultText(block.content) : undefined;
  const errorClass = isError ? ` ${styles.toolResultError}` : "";
  const diffFilePath = isDiffToolContent(block.content) ? block.content.filePath : undefined;

  return (
    <div
      className={getToolLineClassName({ isOpen, isError })}
      onClick={(): void => setIsOpen((prev) => !prev)}
      role="button"
      tabIndex={0}
      aria-expanded={isOpen}
      data-testid={ElementIds.ALPHA_CHAT_TOOL_LINE}
      onKeyDown={(e): void => {
        if (e.key === "Enter" || e.key === " ") setIsOpen((prev) => !prev);
      }}
    >
      <div className={styles.toolHeader}>
        <ChevronRightIcon size={12} className={isOpen ? styles.chevronOpen : styles.chevronClosed} />
        <span className={styles.toolName} data-testid={ElementIds.ALPHA_CHAT_TOOL_NAME}>
          {block.toolName ?? "tool"}
        </span>
        <span className={styles.toolInput}>{invocationSummary}</span>
        {diffFilePath && <DiffPanelButton filePath={diffFilePath} onOpenDiffPanel={onOpenDiffPanel} />}
      </div>
      {isOpen && hasDiffResult && <DiffResult content={block.content as DiffToolContent} />}
      {isOpen && resultText && <pre className={`${styles.toolResult}${errorClass}`}>{resultText}</pre>}
    </div>
  );
};
