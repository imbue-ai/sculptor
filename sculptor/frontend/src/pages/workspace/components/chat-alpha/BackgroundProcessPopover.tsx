// Details popover opened from the BackgroundProcessChip. One row per
// background process — running first, then ended (launch order preserved
// within each group). Status is conveyed without color: running rows pulse
// their type icon, ended rows dim and show a one-word state.
//
// Presentational: the live elapsed time ticks from `startedAt`, but every
// action is delegated to props — `onStopProcess` for the per-process Stop and
// `outputByTaskId` to supply the inline terminal-style output box. Rows with
// output toggle that box open/closed as a single-open accordion.
import { Button } from "@radix-ui/themes";
import type { LucideIcon } from "lucide-react";
import { Activity, Bot, ChevronRightIcon, Terminal } from "lucide-react";
import type { KeyboardEvent, MouseEvent, ReactElement } from "react";
import { useEffect, useState } from "react";

import { mergeClasses, optional } from "~/common/Utils";

import { BackgroundProcessOutputBox } from "./BackgroundProcessOutputBox.tsx";
import styles from "./BackgroundProcessPopover.module.scss";

// Local mirror of the backend `BackgroundProcess` registry model, so this
// popover and its stories build standalone in Storybook without the generated
// `~/api` client. Keep this shape in sync with the backend model when wiring
// the popover to live data.
export type BackgroundProcess = {
  taskId: string;
  toolUseId: string;
  kind: "bash" | "monitor" | "agent";
  name: string;
  status: "running" | "completed" | "failed" | "stopped";
  startedAt: string;
  endedAt?: string | null;
  summary?: string;
  durationSeconds?: number | null;
};

type BackgroundProcessKind = BackgroundProcess["kind"];
type BackgroundProcessStatus = BackgroundProcess["status"];

type ProcessOutput = { command: string; lines: ReadonlyArray<string> };

type BackgroundProcessPopoverProps = {
  processes: ReadonlyArray<BackgroundProcess>;
  onStopProcess?: (taskId: string) => void;
  outputByTaskId?: Readonly<Record<string, ProcessOutput>>;
  // Which row's output box starts open (single-open accordion). Lets a parent
  // render the popover with a row already expanded — primarily for stories and
  // tests; in the app the accordion is driven by user clicks.
  initialExpandedTaskId?: string;
};

const KIND_ICONS = {
  bash: Terminal,
  monitor: Activity,
  agent: Bot,
} as const satisfies Record<BackgroundProcessKind, LucideIcon>;

// One-word state shown in the rightmost slot of an ended row (gray, no color).
const ENDED_STATE_LABELS = {
  completed: "done",
  failed: "failed",
  stopped: "stopped",
} as const satisfies Record<Exclude<BackgroundProcessStatus, "running">, string>;

const isRunning = (process: BackgroundProcess): boolean => process.status === "running";

// Format an elapsed duration: sub-minute → one decimal second ("6.2s");
// otherwise minutes + whole seconds ("2m 14s").
const formatElapsed = (seconds: number): string => {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${minutes}m ${remainder}s`;
};

// Tick once per second while `isActive`, exposing a `now` timestamp that drives
// the live elapsed time on running rows. Idle when nothing is running so the
// popover doesn't re-render needlessly.
const useNow = (isActive: boolean): number => {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    if (!isActive) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return (): void => window.clearInterval(id);
  }, [isActive]);

  return now;
};

const elapsedSeconds = (process: BackgroundProcess, now: number): number => {
  if (isRunning(process)) {
    return Math.max(0, (now - new Date(process.startedAt).getTime()) / 1000);
  }
  const { durationSeconds, endedAt } = process;

  if (durationSeconds !== null && durationSeconds !== undefined) {
    return durationSeconds;
  }

  if (endedAt !== null && endedAt !== undefined) {
    return Math.max(0, (new Date(endedAt).getTime() - new Date(process.startedAt).getTime()) / 1000);
  }

  return 0;
};

const ProcessRow = ({
  process,
  now,
  output,
  isExpanded,
  onToggleExpanded,
  onStopProcess,
}: {
  process: BackgroundProcess;
  now: number;
  output?: ProcessOutput;
  isExpanded: boolean;
  onToggleExpanded: () => void;
  onStopProcess?: (taskId: string) => void;
}): ReactElement => {
  const isProcessRunning = isRunning(process);
  const Icon = KIND_ICONS[process.kind];
  const elapsed = formatElapsed(elapsedSeconds(process, now));
  const hasOutput = output !== undefined;

  // The Stop button lives inside the row; stop its click from also toggling the
  // row's expansion.
  const handleStop = (event: MouseEvent): void => {
    event.stopPropagation();
    onStopProcess?.(process.taskId);
  };

  // The whole row is a button when it has output. Keep it a div with role/key
  // handling rather than a Radix Button so the row keeps its plain list-row
  // layout (a Radix Button would impose button chrome on the full-width row).
  const handleRowKeyDown = (event: KeyboardEvent): void => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggleExpanded();
    }
  };

  const rowContent = (
    <>
      <span className={mergeClasses(styles.icon, optional(isProcessRunning, styles.iconRunning))}>
        <Icon size={14} />
      </span>
      <span className={styles.name}>{process.name}</span>
      <span className={styles.elapsed}>{elapsed}</span>
      <span className={styles.slot}>
        {process.status === "running" ? (
          <Button
            size="1"
            variant="soft"
            color="gray"
            className={styles.stopButton}
            onClick={handleStop}
            title="Stop this process"
          >
            Stop
          </Button>
        ) : (
          ENDED_STATE_LABELS[process.status]
        )}
      </span>
      {/* Expand affordance on the right (subagent-pill style). Rows without
          output get a same-width spacer so the state/Stop column stays aligned. */}
      {hasOutput ? (
        <span className={mergeClasses(styles.chevron, optional(isExpanded, styles.chevronOpen))}>
          <ChevronRightIcon size={14} />
        </span>
      ) : (
        <span className={styles.chevronSpacer} />
      )}
    </>
  );

  return (
    <div className={styles.rowGroup} data-testid="background-process-row">
      {hasOutput ? (
        <div
          role="button"
          tabIndex={0}
          className={mergeClasses(styles.row, styles.rowExpandable, optional(isExpanded, styles.rowActive))}
          onClick={onToggleExpanded}
          onKeyDown={handleRowKeyDown}
          aria-expanded={isExpanded}
        >
          {rowContent}
        </div>
      ) : (
        <div className={styles.row}>{rowContent}</div>
      )}
      {hasOutput && isExpanded ? (
        <div className={styles.output}>
          <BackgroundProcessOutputBox command={output.command} lines={output.lines} isRunning={isProcessRunning} />
        </div>
      ) : undefined}
    </div>
  );
};

export const BackgroundProcessPopover = ({
  processes,
  onStopProcess,
  outputByTaskId,
  initialExpandedTaskId,
}: BackgroundProcessPopoverProps): ReactElement => {
  // Single-open accordion: at most one expanded output box at a time.
  const [expandedTaskId, setExpandedTaskId] = useState<string | undefined>(initialExpandedTaskId);

  // Running first, then ended; launch order is preserved within each group
  // because filter keeps the input order.
  const running = processes.filter(isRunning);
  const ended = processes.filter((process) => !isRunning(process));
  const ordered = [...running, ...ended];

  const now = useNow(running.length > 0);

  const handleToggleExpanded = (taskId: string): void => {
    setExpandedTaskId((current) => (current === taskId ? undefined : taskId));
  };

  return (
    <div className={styles.popoverContent} data-testid="background-process-popover">
      <div className={styles.header}>Background processes</div>
      <div className={styles.list}>
        {ordered.map((process) => (
          <ProcessRow
            key={process.taskId}
            process={process}
            now={now}
            output={outputByTaskId?.[process.taskId]}
            isExpanded={expandedTaskId === process.taskId}
            onToggleExpanded={(): void => handleToggleExpanded(process.taskId)}
            onStopProcess={onStopProcess}
          />
        ))}
      </div>
    </div>
  );
};
