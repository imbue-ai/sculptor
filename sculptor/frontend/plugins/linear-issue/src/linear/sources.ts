import type { LinearIssue } from "./client.ts";

/** Where a ticket in the panel came from. */
export type TicketSource = "branch" | "pr" | "pinned";

export type PanelTicket = {
  issue: LinearIssue;
  /** Every source this issue was found through (an issue can have several). */
  sources: ReadonlyArray<TicketSource>;
  /** The issue linked to the workspace's branch — shown first and accented. */
  isPrimary: boolean;
};

/**
 * Compose the per-source issue lists into one de-duplicated, ordered list. An
 * issue found via several sources keeps a single entry whose `sources` union
 * explains where it came from; insertion order (branch, then PR, then pinned)
 * puts the workspace ticket first.
 */
export const mergeTickets = (inputs: {
  primary: LinearIssue | null;
  prLinked: ReadonlyArray<LinearIssue>;
  pinned: ReadonlyArray<LinearIssue>;
}): ReadonlyArray<PanelTicket> => {
  const byId = new Map<string, { issue: LinearIssue; sources: Array<TicketSource>; isPrimary: boolean }>();

  const add = (issue: LinearIssue, source: TicketSource, isPrimary: boolean): void => {
    const existing = byId.get(issue.identifier);
    if (existing) {
      if (!existing.sources.includes(source)) existing.sources.push(source);
      existing.isPrimary = existing.isPrimary || isPrimary;
      return;
    }
    byId.set(issue.identifier, { issue, sources: [source], isPrimary });
  };

  if (inputs.primary) add(inputs.primary, "branch", true);
  inputs.prLinked.forEach((issue) => add(issue, "pr", false));
  inputs.pinned.forEach((issue) => add(issue, "pinned", false));

  // Map preserves insertion order, so the branch ticket stays first.
  return [...byId.values()].map((entry) => ({
    issue: entry.issue,
    sources: entry.sources,
    isPrimary: entry.isPrimary,
  }));
};
