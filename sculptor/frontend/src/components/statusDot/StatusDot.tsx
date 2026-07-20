import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useId } from "react";

import styles from "./StatusDot.module.scss";
import { dotDiameter, pulseTiming, resolveWorkspaceDotStatuses } from "./statusDotHelpers";
import type { AgentDotStatus, WorkspaceDotStatus } from "./statusUtils";

// Every status is a colored dot of one consistent size: yellow for "waiting on
// your input", red for errors, green for fresh (unread) output, gray once it
// has been seen (read), and blue for running — which additionally pulses (see
// PulseLoader). Each dot is centered in a fixed size-wide slot so the row labels
// next to them stay aligned.
//
// This is the shared renderer for agent and workspace status dots; every
// surface that shows one (sidebar rows, panel tabs, command palette, peek
// popover) renders through it, so a change here stays consistent everywhere.
// The pure sizing/timing/aggregation math lives in statusDotHelpers.ts.

const FilledDot = ({ size, className }: { size: number; className: string }): ReactElement => {
  const diameter = dotDiameter(size);
  return (
    <span className={styles.dotBox} style={{ width: size, height: size }} aria-hidden>
      <span className={`${styles.dot} ${className}`} style={{ width: diameter, height: diameter }} />
    </span>
  );
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
