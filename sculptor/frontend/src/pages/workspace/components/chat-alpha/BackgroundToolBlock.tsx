// A background launch rendered in the chat transcript, mirroring a subagent
// pill (AlphaSubagentPill). Presentational only: status, trailing text, and
// expansion are all prop-driven.
//
// Status is conveyed WITHOUT color: a spinner in the left gutter while running
// (→ a corner-return arrow when ended), the running row pulses gently, ended
// rows dim. The type icon, name/command, and trailing text are all neutral
// gray; the only color allowed is authentic terminal log content inside the
// shared BackgroundProcessOutputBox.
//
// `kind === 'agent'` mirrors today's AlphaSubagentPill EXACTLY — no extra type
// icon or label, just the prompt + dim trailing text + chevron. `bash` and
// `monitor` add a neutral type icon and render the command in mono.
import type { LucideIcon } from "lucide-react";
import { Activity, ChevronRight, CornerDownRight, Terminal } from "lucide-react";
import type { ReactElement } from "react";

import { mergeClasses, optional } from "~/common/Utils";

import { BackgroundProcessOutputBox } from "./BackgroundProcessOutputBox.tsx";
import styles from "./BackgroundToolBlock.module.scss";
import { SpinnerAnimation } from "./pill-animations";

type BackgroundToolBlockKind = "bash" | "monitor" | "agent";
type BackgroundToolBlockStatus = "running" | "exited" | "done";

type BackgroundToolBlockOutput = {
  command: string;
  lines: ReadonlyArray<string>;
};

type BackgroundToolBlockProps = {
  kind: BackgroundToolBlockKind;
  name: string;
  command: string;
  status: BackgroundToolBlockStatus;
  // Caller supplies the fully-resolved, dim mono trailing string, e.g.
  // "background · 2m 14s" or "exited · code 1 · 4m 12s".
  trailingText: string;
  exitCode?: number;
  isExpanded?: boolean;
  output?: BackgroundToolBlockOutput;
};

// Neutral type icons for the command-style kinds. Agent intentionally has no
// entry here — it mirrors the bare subagent pill (no inner type icon/label).
const COMMAND_KIND_ICONS = {
  bash: Terminal,
  monitor: Activity,
} as const satisfies Record<"bash" | "monitor", LucideIcon>;

export const BackgroundToolBlock = ({
  kind,
  name,
  command,
  status,
  trailingText,
  isExpanded,
  output,
}: BackgroundToolBlockProps): ReactElement => {
  const isRunning = status === "running";
  const isShowingOutput = (isExpanded ?? false) && output !== undefined;

  // Agent blocks render exactly like the subagent pill: just the prompt, the
  // dim trailing text, and the chevron — no type icon, no label.
  const isAgent = kind === "agent";
  const TypeIcon = isAgent ? undefined : COMMAND_KIND_ICONS[kind];

  // The pill content is the prompt (agent) or the command (bash/monitor). The
  // name leads agent blocks just like the subagent prompt; bash/monitor lead
  // with the command in mono.
  const primaryText = isAgent ? name : command;

  return (
    <div className={styles.root}>
      <div className={mergeClasses(styles.row, optional(!isRunning, styles.rowEnded))}>
        <span className={styles.gutterIcon}>{isRunning ? <SpinnerAnimation /> : <CornerDownRight size={14} />}</span>
        <div className={mergeClasses(styles.pill, optional(isRunning, styles.pillRunning))}>
          {TypeIcon !== undefined ? <TypeIcon size={14} className={styles.typeIcon} aria-hidden="true" /> : undefined}
          <span className={mergeClasses(styles.primary, optional(!isAgent, styles.primaryMono))} title={primaryText}>
            {primaryText}
          </span>
          <span className={styles.trailing}>{trailingText}</span>
          <ChevronRight
            size={14}
            className={mergeClasses(styles.chevron, optional(isExpanded ?? false, styles.chevronOpen))}
          />
        </div>
      </div>
      {isShowingOutput ? (
        <div className={styles.output}>
          <BackgroundProcessOutputBox command={output.command} lines={output.lines} isRunning={isRunning} />
        </div>
      ) : undefined}
    </div>
  );
};
