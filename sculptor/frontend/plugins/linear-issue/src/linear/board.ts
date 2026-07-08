import { type WorkspaceLink, workspacesForIssue } from "./association.ts";
import type { LinearIssue } from "./client.ts";

/** One ticket on the board, with whatever workspaces are working on it. */
export type BoardRow<T extends WorkspaceLink> = {
  issue: LinearIssue;
  /** Workspaces associated with this issue (empty when none exists yet). */
  workspaces: ReadonlyArray<T>;
};

/** A run of board tickets that share a workflow state, shown under one header. */
export type BoardGroup<T extends WorkspaceLink> = {
  /** Stable key for React lists: the state's type and name. */
  key: string;
  /** Display name of the workflow state (e.g. "In Progress"). */
  stateName: string;
  /** Linear's `state.type`, or `null` for issues with no state. */
  stateType: string | null;
  /** The state's display color, or `null` when unknown. */
  color: string | null;
  rows: ReadonlyArray<BoardRow<T>>;
  /** Rows dropped from `rows` by the terminal-state cap (0 for active states). */
  hiddenCount: number;
};

/** Pre-fill values for the host's new-workspace modal, derived from a ticket. */
export type WorkspaceSeed = {
  title: string;
  prompt: string;
};

/**
 * Build the new-workspace title and prompt for a ticket. The title leads with
 * the identifier because the host derives the branch name from the title — so
 * the generated branch carries the ticket id, which is also how the board
 * associates branches back to tickets. The prompt is a short self-contained
 * brief: the assignment, the issue URL, and the description when there is one.
 */
export const workspaceSeedForIssue = (issue: LinearIssue): WorkspaceSeed => {
  const promptLines = [`Work on Linear issue ${issue.identifier}: ${issue.title}`, issue.url];
  if (issue.description) {
    promptLines.push("", issue.description);
  }
  return {
    title: `${issue.identifier}: ${issue.title}`,
    prompt: promptLines.join("\n"),
  };
};

// Group order: active work first, terminal states last. Anything Linear adds
// that we don't know sorts after the known types but before nothing.
const TYPE_ORDER: Record<string, number> = {
  started: 0,
  unstarted: 1,
  triage: 2,
  backlog: 3,
  completed: 4,
  canceled: 5,
};
const UNKNOWN_TYPE_ORDER = 6;

// Terminal states are kept only as a recent sample: the issue list is ordered
// most-recently-updated first, so the cap keeps a handful of just-finished
// tickets visible without letting a long completion history bury active work.
const TERMINAL_TYPES = new Set(["completed", "canceled"]);
const TERMINAL_ROW_CAP = 8;

const typeRank = (type: string | null): number =>
  type ? (TYPE_ORDER[type] ?? UNKNOWN_TYPE_ORDER) : UNKNOWN_TYPE_ORDER;

/**
 * Group assigned issues by workflow state for the board, attaching each issue's
 * associated workspaces. Groups are ordered active-first (by `state.type`), then
 * by Linear's within-team `position`, then by name. The name tiebreak matters
 * because assigned issues can span teams and `position` only orders states
 * within one team — without it, two same-type groups from different teams would
 * sort arbitrarily. Rows preserve the input order (most recently updated first).
 * Terminal-state groups are capped, surfacing the overflow as `hiddenCount`
 * rather than dropping it silently.
 */
export const buildBoard = <T extends WorkspaceLink>(
  issues: ReadonlyArray<LinearIssue>,
  workspaces: ReadonlyArray<T>,
): ReadonlyArray<BoardGroup<T>> => {
  type Bucket = {
    stateName: string;
    stateType: string | null;
    color: string | null;
    position: number;
    rows: Array<BoardRow<T>>;
  };
  const buckets = new Map<string, Bucket>();

  for (const issue of issues) {
    const key = issue.state ? `${issue.state.type}:${issue.state.name}` : "none";
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = {
        stateName: issue.state?.name ?? "No status",
        stateType: issue.state?.type ?? null,
        color: issue.state?.color ?? null,
        // Issues without a position sort after positioned ones in the same type.
        position: issue.state?.position ?? Number.MAX_SAFE_INTEGER,
        rows: [],
      };
      buckets.set(key, bucket);
    }
    bucket.rows.push({ issue, workspaces: workspacesForIssue(issue, workspaces) });
  }

  return [...buckets.entries()]
    .sort(([, a], [, b]) => {
      const byType = typeRank(a.stateType) - typeRank(b.stateType);
      if (byType !== 0) return byType;
      // `position` is within-team; fall back to name so cross-team groups of the
      // same type order deterministically rather than by Map insertion order.
      return a.position - b.position || a.stateName.localeCompare(b.stateName);
    })
    .map(([key, bucket]) => {
      const isTerminal = bucket.stateType !== null && TERMINAL_TYPES.has(bucket.stateType);
      const cap = isTerminal ? TERMINAL_ROW_CAP : bucket.rows.length;
      return {
        key,
        stateName: bucket.stateName,
        stateType: bucket.stateType,
        color: bucket.color,
        rows: bucket.rows.slice(0, cap),
        hiddenCount: Math.max(0, bucket.rows.length - cap),
      };
    });
};
