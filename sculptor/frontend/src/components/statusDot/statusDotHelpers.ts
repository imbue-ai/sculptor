// Pure helpers extracted from StatusDot so the .tsx file can keep its
// component-only exports (Fast Refresh requires component files to export
// only components; mixing helpers + components breaks HMR per
// react-refresh/only-export-components).
import type { CSSProperties } from "react";

import type { AgentDotStatus, WorkspaceDotStatus } from "./statusUtils";

// The dot diameter as a fraction of the slot; a little inset off the slot edges
// keeps the dots from crowding their row labels.
export const DOT_SCALE = 0.75;

export const dotDiameter = (size: number): number => Math.round(size * DOT_SCALE);

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
export const pulseTiming = (seed: string): { halo: CSSProperties; haloTrailing: CSSProperties } => {
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
 * Collapses a workspace's aggregate agent status into the one or two agent
 * dots shown for it.
 *
 * When some (but not all) agents have errors, two dots are shown: the error
 * dot plus whichever of running/waiting/ready best summarises the rest.
 */
export const resolveWorkspaceDotStatuses = (status: WorkspaceDotStatus): ReadonlyArray<AgentDotStatus> => {
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
