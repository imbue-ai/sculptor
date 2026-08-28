import type { KeyboardEvent, ReactElement } from "react";
import { createElement, forwardRef, memo, useCallback } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";

import { formatDuration } from "./durationUtils.ts";
import styles from "./ExpandedToolRow.module.scss";
import type { PillData } from "./toolPill.types.ts";
import { getToolIcon } from "./toolPillIcons.tsx";
import { ToolEntryContent, type ToolEntryShell } from "./ToolPopover.tsx";
import { useElapsedTime } from "./useElapsedTime.ts";

type ExpandedToolRowProps = {
  pillData: PillData;
  workspaceCodePath: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onFocus?: () => void;
  tabIndex?: 0 | -1;
};

/**
 * Single-row presentation of a tool call for "expanded" chat density.
 * Mirrors the popover header content (title / meta / actions) inlined on
 * the row, with a leading icon + tool name. The popover itself is
 * unchanged — clicking or hovering still opens it.
 *
 * The row is a div with role="button" rather than a real button so the
 * Read tool's action IconButtons can sit inside it without nesting.
 *
 * Wrapped in `memo` so unrelated re-renders of the parent (e.g. another
 * pill in the same row opening its popover) don't cascade into every row
 * recomputing its title/meta/actions. Pair with stable callback props at
 * the call site.
 */
const ExpandedToolRowImpl = forwardRef<HTMLDivElement, ExpandedToolRowProps>(
  ({ pillData, workspaceCodePath, isOpen, onToggle, onFocus, tabIndex }, ref): ReactElement => {
    const { state, label } = pillData;
    // Command-style rendering applies to tools whose input block carries a
    // `command` + optional `description` (Bash and Monitor today). They share
    // a row layout, popover, and pulsing status dot while executing.
    const isCommandStyleTool = label === "Bash" || label === "Monitor";
    const isExecuting = state === "initializing";
    const Icon = getToolIcon(label);
    const isShowingStatusDot = isCommandStyleTool && isExecuting;

    const handleKeyDown = useCallback(
      (e: KeyboardEvent<HTMLDivElement>): void => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      },
      [onToggle],
    );

    const classNames = [styles.row];
    if (isOpen) classNames.push(styles.rowOpen);
    if (state === "error") classNames.push(styles.rowError);

    const block = pillData.blocks[0] ?? null;
    const result = pillData.results[0] ?? null;

    // Expanded rows deliberately drop the per-tool action buttons (copy
    // path, open in editor, etc.). The whole row is a click target that
    // opens the popover, where the same actions are still available — and
    // a row crowded with icon buttons fights with its job of reading like
    // a quick-scan summary line.
    const rowShell: ToolEntryShell = ({ title, meta }) => (
      <>
        <span className={styles.rowTitle}>{title}</span>
        {meta !== undefined && (
          <span className={styles.rowAside}>
            <span className={styles.rowMeta}>{meta}</span>
          </span>
        )}
      </>
    );

    // Bash keeps its dedicated testID so the existing integration tests stay
    // anchored to it; Monitor and everything else share the generic pill ID.
    const testId = label === "Bash" ? ElementIds.ALPHA_CHAT_BASH_BLOCK : ElementIds.ALPHA_CHAT_TOOL_PILL;

    return (
      <div
        ref={ref}
        role="button"
        aria-pressed={isOpen}
        tabIndex={tabIndex}
        className={classNames.join(" ")}
        onClick={onToggle}
        onFocus={onFocus}
        onKeyDown={handleKeyDown}
        data-testid={testId}
        data-tool-state={state}
      >
        <span className={styles.rowLeading}>
          {isShowingStatusDot ? (
            <span className={`${styles.statusDot} ${styles.statusDotPulsing}`} aria-label="executing" />
          ) : (
            // Icon is selected from module-level tool icons (getToolIcon), not
            // created during render; createElement keeps that explicit.
            createElement(Icon, { className: styles.rowIcon, "aria-hidden": true })
          )}
          <span className={state === "error" ? styles.rowLabelError : styles.rowLabel}>{label}</span>
          <span className={styles.rowSeparator} aria-hidden="true">
            ·
          </span>
        </span>
        {isCommandStyleTool ? (
          <CommandRowContent block={block} result={result} isExecuting={isExecuting} shell={rowShell} />
        ) : (
          <ToolEntryContent
            toolName={label}
            block={block}
            result={result}
            workspaceCodePath={workspaceCodePath}
            renderShell={rowShell}
          />
        )}
      </div>
    );
  },
);

ExpandedToolRowImpl.displayName = "ExpandedToolRow";

export const ExpandedToolRow = memo(ExpandedToolRowImpl);

// Shared row branch for shell-command-style tools (Bash, Monitor). Their
// primary popover (CommandPopover) shows description + duration in
// the header, not the command — this row mirrors that so the summary line
// matches what the popover would surface. `useElapsedTime` ticks while
// executing.
//
// Layout: [description] [command (truncated)]. The command is rendered as
// a single-line inline-block with text-overflow: ellipsis, so when the row
// is tight it loses characters from the right rather than letting the
// description, leading tool label, or duration meta truncate.
const CommandRowContent = ({
  block,
  result,
  isExecuting,
  shell,
}: {
  block: ToolUseBlock | null;
  result: ToolResultBlock | null;
  isExecuting: boolean;
  shell: ToolEntryShell;
}): ReactElement => {
  const command =
    (block?.input?.command as string | undefined) ?? result?.invocationString ?? block?.name ?? result?.toolName ?? "";
  const description = (block?.input?.description as string | undefined) ?? result?.description ?? "";
  const persistKey = block?.id ?? result?.toolUseId ?? "";
  const { elapsed } = useElapsedTime(true, isExecuting, persistKey);
  const elapsedSeconds = parseFloat(elapsed);
  const duration = formatDuration(isExecuting ? elapsedSeconds : (result?.durationSeconds ?? elapsedSeconds));

  const title = (
    <span className={styles.commandTitle}>
      {description && <span className={styles.commandDescription}>{description}</span>}
      <span className={styles.commandTrail}>
        <span className={styles.commandPrompt} aria-hidden="true">
          $
        </span>{" "}
        {command}
      </span>
    </span>
  );

  return shell({ title, meta: duration, bodyText: "" });
};
