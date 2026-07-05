import { IconButton, Tooltip } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import { Check, CopyIcon, ExternalLink } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { isGenericToolContent } from "~/common/Guards.ts";
import { openFileViewTabAtom } from "~/pages/workspace/diffPanel/atoms.ts";

import styles from "./AlphaToolPopover.module.scss";
import { useChatTask } from "./ChatTaskContext.tsx";
import { OutsideWorkspaceIcon } from "./OutsideWorkspaceIcon.tsx";
import headerStyles from "./PopoverHeader.module.scss";
import { PopoverHeader } from "./PopoverHeader.tsx";
import type { PillData } from "./toolPill.types.ts";
import { makeRelative } from "./toolPillUtils.ts";

export type ToolEntryShellArgs = {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  /** Body text. The popover shell renders this as <pre>; the row shell ignores it. */
  bodyText: string;
  /** Extra className for the body — e.g. terminal background or error tint. */
  bodyClassName?: string;
};

/**
 * Render-prop callback that decides how a per-tool entry is laid out.
 * Used by the popover (default) to render header + body, and by the
 * expanded row mode to inline header content next to the tool icon.
 */
export type ToolEntryShell = (args: ToolEntryShellArgs) => ReactElement;

type ToolEntryProps = {
  block: ToolUseBlock | null;
  result: ToolResultBlock | null;
  workspaceCodePath: string | null;
  /** Defaults to the popover-entry layout (header + body). */
  renderShell?: ToolEntryShell;
};

const defaultPopoverShell: ToolEntryShell = ({ title, meta, actions, bodyText, bodyClassName }) => (
  <div className={styles.entry}>
    <PopoverHeader title={title} meta={meta} actions={actions} />
    {bodyText && <pre className={bodyClassName ?? styles.entryBody}>{bodyText}</pre>}
  </div>
);

const getResultText = (result: ToolResultBlock | null): string => {
  if (!result) return "";
  if (isGenericToolContent(result.content)) return result.content.text;
  return "";
};

const ReadEntry = ({
  block,
  result,
  workspaceCodePath,
  renderShell = defaultPopoverShell,
}: ToolEntryProps): ReactElement => {
  // Result-only blocks (completed sessions) carry the invoked file path on the
  // result's invocationString rather than block.input — fall back to that.
  const rawPath = (block?.input?.file_path as string | undefined) ?? result?.invocationString ?? "";
  const { display: filePath, isOutsideWorkspace } = makeRelative(rawPath, workspaceCodePath);
  const startLine = block?.input?.start_line as number | undefined;
  const endLine = block?.input?.end_line as number | undefined;
  const lineRange = startLine !== undefined ? ` :${startLine}${endLine !== undefined ? `–${endLine}` : ""}` : "";
  const text = getResultText(result);
  const lineCount = text ? text.trimEnd().split("\n").length : null;

  const { workspaceId: workspaceID } = useChatTask();
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const [isCopied, setIsCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => (): void => clearTimeout(copyTimerRef.current), []);

  const handleCopyPath = useCallback(
    (e: React.MouseEvent): void => {
      e.stopPropagation();
      if (!filePath) return;
      navigator.clipboard.writeText(filePath).catch(() => {});
      setIsCopied(true);
      clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setIsCopied(false), 1500);
    },
    [filePath],
  );

  const handleOpenFile = useCallback(
    (e: React.MouseEvent): void => {
      e.stopPropagation();
      if (!filePath) return;
      openFileViewTab({ workspaceId: workspaceID, filePath });
    },
    [openFileViewTab, workspaceID, filePath],
  );

  const title = (
    <span className={headerStyles.titleCode}>
      {isOutsideWorkspace && <OutsideWorkspaceIcon />}
      {filePath}
      {lineRange}
    </span>
  );
  const actions = filePath ? (
    <>
      <Tooltip content="Copy file path">
        <IconButton
          variant="ghost"
          size="1"
          className={styles.entryActionButton}
          onClick={handleCopyPath}
          aria-label="Copy file path"
        >
          {isCopied ? <Check size={14} /> : <CopyIcon size={14} />}
        </IconButton>
      </Tooltip>
      {!isOutsideWorkspace && (
        <Tooltip content="Open file in Sculptor">
          <IconButton
            variant="ghost"
            size="1"
            className={styles.entryActionButton}
            onClick={handleOpenFile}
            aria-label="Open file in Sculptor"
          >
            <ExternalLink size={14} />
          </IconButton>
        </Tooltip>
      )}
    </>
  ) : undefined;

  return renderShell({
    title,
    meta: lineCount !== null ? `${lineCount} lines` : undefined,
    actions,
    bodyText: text,
  });
};

// Shared entry layout for shell-command-style tools (Bash, Monitor) — both
// surface a `command` and an optional `description` on their input block.
// The description sits above the command in the title slot, mirroring the
// single-call AlphaCommandPopover.
const CommandEntry = ({ block, result, renderShell = defaultPopoverShell }: ToolEntryProps): ReactElement => {
  const command =
    (block?.input?.command as string | undefined) ?? result?.invocationString ?? block?.name ?? result?.toolName ?? "";
  const description = (block?.input?.description as string | undefined) ?? result?.description ?? "";
  const text = getResultText(result);

  const title = (
    <>
      {description && <span className={styles.entryDescription}>{description}</span>}
      <span className={headerStyles.titleCode}>{command}</span>
    </>
  );

  return renderShell({
    title,
    bodyText: text,
    bodyClassName: `${styles.entryBody} ${styles.entryBodyTerminal}`,
  });
};

const GrepEntry = ({
  block,
  result,
  workspaceCodePath,
  renderShell = defaultPopoverShell,
}: ToolEntryProps): ReactElement => {
  const pattern = block?.input?.pattern as string | undefined;
  const rawPath = block?.input?.path as string | undefined;
  const relativePath = rawPath ? makeRelative(rawPath, workspaceCodePath) : undefined;
  const text = getResultText(result);
  const matchCount = text ? text.split("\n").filter((l) => l.trim()).length : null;
  // Result-only blocks: backend formats invocationString as `"pattern" in path`
  // (or just `"pattern"`), so use it verbatim when block.input is unavailable.
  const fallbackInvocation = !pattern && result?.invocationString ? result.invocationString : null;

  // The pattern + " in /path" reads as a unit ("what was searched"), so it
  // belongs in the title — that way long values wrap together on the left and
  // the meta slot stays small in the top-right.
  let title: ReactNode = "";
  if (pattern) {
    title = (
      <>
        <span className={headerStyles.titleCode}>&quot;{pattern}&quot;</span>
        {relativePath && (
          <>
            <span className={headerStyles.titleConnector}> in </span>
            {relativePath.isOutsideWorkspace && <OutsideWorkspaceIcon />}
            <span className={headerStyles.titleCode}>{relativePath.display}</span>
          </>
        )}
      </>
    );
  } else if (fallbackInvocation) {
    title = <span className={headerStyles.titleCode}>{fallbackInvocation}</span>;
  }

  return renderShell({
    title,
    meta: matchCount !== null ? `${matchCount} matches` : undefined,
    bodyText: text,
  });
};

const GlobEntry = ({ block, result, renderShell = defaultPopoverShell }: ToolEntryProps): ReactElement => {
  const pattern = (block?.input?.pattern as string | undefined) ?? result?.invocationString;
  const text = getResultText(result);
  const fileCount = text ? text.split("\n").filter((l) => l.trim()).length : null;

  return renderShell({
    title: pattern ? <span className={headerStyles.titleCode}>{pattern}</span> : "",
    meta: fileCount !== null ? `${fileCount} files` : undefined,
    bodyText: text,
  });
};

const WebEntry = ({ block, result, renderShell = defaultPopoverShell }: ToolEntryProps): ReactElement => {
  const url =
    (block?.input?.url as string | undefined) ??
    (block?.input?.query as string | undefined) ??
    result?.invocationString ??
    "";
  const text = getResultText(result);

  return renderShell({
    title: <span className={headerStyles.titleCode}>{url}</span>,
    bodyText: text,
  });
};

const DefaultEntry = ({ block, result, renderShell = defaultPopoverShell }: ToolEntryProps): ReactElement => {
  const name = block?.name ?? result?.toolName ?? "tool";
  const invocation = (block?.invocationString as string | undefined) ?? result?.invocationString ?? "";
  const text = getResultText(result);

  // Use the invocation as the title (it's the descriptive call — the tool
  // name is already shown on the pill above). Falls back to the bare tool
  // name when there's no invocation. Putting the invocation here instead of
  // in `meta` lets long values like `select:CronList,CronCreate,...` wrap
  // cleanly in the title column rather than overflowing the pinned meta slot.
  const title = <span className={headerStyles.titleCode}>{invocation || name}</span>;
  const bodyClassName = result?.isError ? `${styles.entryBody} ${styles.entryBodyError}` : styles.entryBody;

  return renderShell({
    title,
    bodyText: text,
    bodyClassName,
  });
};

type ToolEntryContentProps = {
  toolName: string;
  block: ToolUseBlock | null;
  result: ToolResultBlock | null;
  workspaceCodePath: string | null;
  /** Defaults to the popover-entry layout (header + body). */
  renderShell?: ToolEntryShell;
};

/**
 * Render a single tool call's per-tool entry. The `renderShell` prop
 * controls layout — popover-entry chrome by default; AlphaToolPillRow
 * passes a row-layout shell for expanded density.
 */
export const ToolEntryContent = ({
  toolName,
  block,
  result,
  workspaceCodePath,
  renderShell,
}: ToolEntryContentProps): ReactElement => {
  const props = { block, result, workspaceCodePath, renderShell };
  switch (toolName) {
    case "Read":
    case "NotebookRead":
    case "LS":
      return <ReadEntry {...props} />;
    case "Bash":
    case "Monitor":
      return <CommandEntry {...props} />;
    case "Grep":
      return <GrepEntry {...props} />;
    case "Glob":
      return <GlobEntry {...props} />;
    case "WebFetch":
    case "WebSearch":
      return <WebEntry {...props} />;
    default:
      return <DefaultEntry {...props} />;
  }
};

type AlphaToolPopoverProps = {
  pillData: PillData;
  workspaceCodePath?: string | null;
};

export const AlphaToolPopover = ({ pillData, workspaceCodePath = null }: AlphaToolPopoverProps): ReactElement => {
  const { blocks, results, label } = pillData;

  // Pair each block with its result. For result-only pills (completed sessions),
  // blocks may be empty — render from results directly.
  const entries: Array<{ block: ToolUseBlock | null; result: ToolResultBlock | null; key: string }> = [];

  if (blocks.length > 0) {
    const resultMap = new Map(results.map((r) => [r.toolUseId, r]));
    for (const block of blocks) {
      entries.push({ block, result: resultMap.get(block.id) ?? null, key: block.id });
    }
  } else {
    for (const result of results) {
      entries.push({ block: null, result, key: result.toolUseId });
    }
  }

  const hasMultipleEntries = blocks.length > 1 || results.length > 1;

  return (
    <div className={styles.popover}>
      {hasMultipleEntries && <PopoverHeader title={label} meta={`${entries.length} calls`} />}
      <div className={styles.body}>
        {entries.map(({ block, result, key }) => {
          const toolName = block?.name ?? result?.toolName ?? "";
          return (
            <ToolEntryContent
              key={key}
              toolName={toolName}
              block={block}
              result={result}
              workspaceCodePath={workspaceCodePath}
            />
          );
        })}
      </div>
    </div>
  );
};
