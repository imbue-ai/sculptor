import { Flex } from "@radix-ui/themes";
import type { CSSProperties, ReactElement } from "react";
import { useId } from "react";

import styles from "./StatusDot.module.scss";
import type { AgentDotStatus, WorkspaceDotStatus } from "./statusUtils";

// Every status is a colored dot of one consistent size: yellow for "waiting on
// your input", red for errors, green for fresh (unread) output, gray once it
// has been seen (read), and blue for running — which additionally pulses (see
// PulseLoader). Each dot is centered in a fixed size-wide slot so the row labels
// next to them stay aligned.
//
// This is the single visual source of truth for status iconography; every
// surface (sidebar rows, panel tabs, command palette, peek popover) renders
// through it, so a change here stays consistent everywhere.

// The dot diameter as a fraction of the slot; a little inset off the slot edges
// keeps the dots from crowding their row labels.
const DOT_SCALE = 0.75;

const dotDiameter = (size: number): number => Math.round(size * DOT_SCALE);

const FilledDot = ({ size, className }: { size: number; className: string }): ReactElement => {
  const diameter = dotDiameter(size);
  return (
    <span className={styles.dotBox} style={{ width: size, height: size }} aria-hidden>
      <span className={`${styles.dot} ${className}`} style={{ width: diameter, height: diameter }} />
    </span>
  );
};

// Stable hash so each running dot derives its own tempo and starting phase from
// a seed — small changes in the seed spread widely.
const hashSeed = (seed: string): number => {
  let hash = 0;
  for (let index = 0; index < seed.length; index++) {
    hash = (hash * 31 + seed.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
};

// Turn a seed into per-instance timing for the two halos. Both share a slightly
// varied loop duration; a negative delay starts each dot partway through its
// cycle (no startup jump), and the second halo trails the first by half a loop
// so the two pings always alternate. A column of running dots then pulses at
// different tempos and phases instead of in lockstep.
const pulseTiming = (seed: string): { halo: CSSProperties; haloTrailing: CSSProperties } => {
  const hash = hashSeed(seed);
  const duration = 1.7 + (hash % 60) / 100; // 1.70s – 2.29s
  const phase = ((Math.floor(hash / 7) % 100) / 100) * duration;
  return {
    halo: { animationDuration: `${duration.toFixed(2)}s`, animationDelay: `${(-phase).toFixed(2)}s` },
    haloTrailing: {
      animationDuration: `${duration.toFixed(2)}s`,
      animationDelay: `${(-phase - duration / 2).toFixed(2)}s`,
    },
  };
};

/**
 * The running state: a solid dot (the same size as the unread/read dots) with
 * two halos pinging outward from it in sequence.
 */
const PulseLoader = ({ size, seed }: { size: number; seed: string }): ReactElement => {
  const { halo, haloTrailing } = pulseTiming(seed);
  const diameter = dotDiameter(size);
  const dotSize = { width: diameter, height: diameter };
  return (
    <span className={styles.pulseBox} style={{ width: size, height: size }} aria-hidden>
      <span className={styles.pulseHalo} style={{ ...dotSize, ...halo }} />
      <span className={styles.pulseHalo} style={{ ...dotSize, ...haloTrailing }} />
      <span className={styles.pulseCore} style={dotSize} />
    </span>
  );
};

type AgentStatusDotProps = {
  status: AgentDotStatus;
  size?: number;
};

const STATUS_DOT_CLASS: Record<Exclude<AgentDotStatus, "running">, string> = {
  waiting: styles.waiting,
  error: styles.error,
  unread: styles.unread,
  read: styles.read,
};

/** Renders a single colored status dot; the running dot additionally pulses. */
export const AgentStatusDot = ({ status, size = 11 }: AgentStatusDotProps): ReactElement => {
  // A per-instance seed so each running dot pulses a little differently. It is
  // stable for the component's lifetime, so the motion doesn't restart on
  // re-render (e.g. a streaming status tick).
  const instanceId = useId();

  if (status === "running") {
    return <PulseLoader size={size} seed={instanceId} />;
  }

  return <FilledDot size={size} className={STATUS_DOT_CLASS[status]} />;
};

/**
 * Collapses a workspace's aggregate agent status into the one or two agent
 * dots shown for it.
 *
 * When some (but not all) agents have errors, two dots are shown: the error
 * dot plus whichever of running/waiting/ready best summarises the rest.
 */
const resolveWorkspaceDotStatuses = (status: WorkspaceDotStatus): ReadonlyArray<AgentDotStatus> => {
  if (status.hasError && !status.isAllError) {
    const secondary: AgentDotStatus = status.hasRunning
      ? "running"
      : status.hasWaiting
        ? "waiting"
        : status.hasUnread
          ? "unread"
          : "read";
    return ["error", secondary];
  }

  if (status.isAllError) {
    return ["error"];
  }

  if (status.hasWaiting) {
    return ["waiting"];
  }

  if (status.hasRunning) {
    return ["running"];
  }

  return [status.hasUnread ? "unread" : "read"];
};

type WorkspaceStatusDotsProps = {
  status: WorkspaceDotStatus;
  size?: number;
};

/** Renders one or two dots summarising a workspace's aggregate agent status. */
export const WorkspaceStatusDots = ({ status, size = 11 }: WorkspaceStatusDotsProps): ReactElement => {
  const statuses = resolveWorkspaceDotStatuses(status);

  if (statuses.length === 1) {
    return <AgentStatusDot status={statuses[0]} size={size} />;
  }

  return (
    <Flex align="center" gap="1">
      {statuses.map((agentStatus) => (
        <AgentStatusDot key={agentStatus} status={agentStatus} size={size} />
      ))}
    </Flex>
  );
};
