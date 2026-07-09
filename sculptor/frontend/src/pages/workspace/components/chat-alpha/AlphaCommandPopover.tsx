import { IconButton, Tooltip } from "@radix-ui/themes";
import { Check, CopyIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import { isGenericToolContent } from "~/common/Guards.ts";

import styles from "./AlphaCommandPopover.module.scss";
import { formatDuration } from "./durationUtils.ts";
import headerStyles from "./PopoverHeader.module.scss";
import { PopoverHeader } from "./PopoverHeader.tsx";
import { useElapsedTime } from "./useElapsedTime.ts";

// Tools that share the command-popover layout. Both surface a `command`
// and an optional `description` on their input block, both stream stdout
// text into a single output body, and both want a live elapsed-time meta
// while running. Bash keeps its dedicated output testID for existing
// integration tests; Monitor doesn't need one yet.
type CommandPopoverToolName = "Bash" | "Monitor";

/** How long a copy button shows its "copied" confirmation before reverting. */
const COPY_FEEDBACK_DURATION_MS = 1500;

type AlphaCommandPopoverProps = {
  toolName: CommandPopoverToolName;
  block: ToolUseBlock | undefined;
  result: ToolResultBlock | undefined;
  isExecuting: boolean;
};

export const AlphaCommandPopover = ({
  toolName,
  block,
  result,
  isExecuting,
}: AlphaCommandPopoverProps): ReactElement => {
  const command =
    (block?.input?.command as string | undefined) ??
    result?.invocationString ??
    block?.name ??
    result?.toolName ??
    toolName;
  const description = (block?.input?.description as string | undefined) ?? result?.description ?? "";
  const outputText = result && isGenericToolContent(result.content) ? result.content.text : "";

  const persistKey = block?.id ?? result?.toolUseId ?? "";
  const { elapsed } = useElapsedTime(true, isExecuting, persistKey);
  const elapsedSeconds = parseFloat(elapsed);
  const duration = formatDuration(isExecuting ? elapsedSeconds : (result?.durationSeconds ?? elapsedSeconds));

  const [isCommandCopied, setIsCommandCopied] = useState<boolean>(false);
  const [isOutputCopied, setIsOutputCopied] = useState<boolean>(false);
  const commandCopyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const outputCopyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(
    () => (): void => {
      clearTimeout(commandCopyTimerRef.current);
      clearTimeout(outputCopyTimerRef.current);
    },
    [],
  );

  const handleCopyCommand = useCallback(
    (e: React.MouseEvent): void => {
      e.stopPropagation();
      navigator.clipboard.writeText(command).catch((error) => {
        console.warn("Failed to copy command to clipboard.", error);
      });
      setIsCommandCopied(true);
      clearTimeout(commandCopyTimerRef.current);
      commandCopyTimerRef.current = setTimeout(() => setIsCommandCopied(false), COPY_FEEDBACK_DURATION_MS);
    },
    [command],
  );

  const handleCopyOutput = useCallback(
    (e: React.MouseEvent): void => {
      e.stopPropagation();
      navigator.clipboard.writeText(outputText).catch((error) => {
        console.warn("Failed to copy output to clipboard.", error);
      });
      setIsOutputCopied(true);
      clearTimeout(outputCopyTimerRef.current);
      outputCopyTimerRef.current = setTimeout(() => setIsOutputCopied(false), COPY_FEEDBACK_DURATION_MS);
    },
    [outputText],
  );

  // Auto-scroll to the bottom while output is streaming.
  const outputRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (isExecuting && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [isExecuting, outputText]);

  // Title slot: human-readable description on top (when set), with the
  // command rendered in code styling below. The popover still shares the
  // monospace `.titleCode` typography with every other tool popover (Read,
  // Grep, etc.) — the description just leads above it as the primary
  // descriptor when one is provided.
  const title = (
    <>
      {description && <span className={styles.description}>{description}</span>}
      <span className={headerStyles.titleCode}>{command}</span>
    </>
  );

  const headerActions = (
    <Tooltip content="Copy command">
      <IconButton variant="ghost" size="1" onClick={handleCopyCommand} aria-label="Copy command">
        {isCommandCopied ? <Check size={14} /> : <CopyIcon size={14} />}
      </IconButton>
    </Tooltip>
  );

  return (
    <div className={styles.popover}>
      <PopoverHeader title={title} meta={duration} actions={headerActions} />
      <div className={styles.popoverSection}>
        <Tooltip content="Copy output">
          <IconButton
            variant="ghost"
            size="1"
            className={styles.copyButton}
            onClick={handleCopyOutput}
            aria-label="Copy output"
          >
            {isOutputCopied ? <Check size={14} /> : <CopyIcon size={14} />}
          </IconButton>
        </Tooltip>
        <div
          ref={outputRef}
          className={styles.popoverBody}
          data-testid={toolName === "Bash" ? ElementIds.ALPHA_CHAT_BASH_OUTPUT : undefined}
        >
          {outputText}
          {isExecuting && <span className={styles.streamCursor} />}
        </div>
      </div>
    </div>
  );
};
