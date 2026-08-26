import { isPullRequestAttachment, type LinearIssue } from "./client.ts";
import { parseTicket } from "./ticket.ts";

/**
 * The canonical mapping between a Sculptor workspace and a Linear issue, in one
 * place so the panel (which resolves one workspace's issue) and the board (which
 * matches many issues against many workspaces) can never drift on what "this
 * workspace is working on that ticket" means.
 *
 * A workspace is associated with an issue when any signal holds:
 *  - it is explicitly assigned to the ticket (the per-workspace assignment the
 *    panel/banner sets — the user's own assertion, so it wins over the branch), or
 *  - its branch name carries the ticket identifier (e.g. `dev/scu-1495-x`), or
 *  - its pull request is one of the issue's linked PR attachments.
 *
 * The first two collapse to a single id via `workspaceTicketId`; the PR signal
 * lives on the issue (its attachments), so it is matched separately. All are
 * read from data already in hand — the explicit assignment and the branch are on
 * the workspace, the PR link is on the fetched issue — so the board never has to
 * re-resolve anything per workspace. (This mirrors the local tiers of the
 * panel's `fetchPrimaryIssue`, minus Linear's server-side `issueVcsBranchSearch`,
 * which the board, matching against an already-fetched issue list, can't replay.)
 */

/** The Linear identifier a branch name points at (e.g. "SCU-1495"), or `null`. */
export const branchTicketId = (branch: string | null): string | null => parseTicket(branch)?.identifier ?? null;

/** A workspace reduced to just the fields that associate it with a ticket. */
export type WorkspaceLink = {
  branch: string | null;
  pullRequestUrl: string | null;
  /**
   * The ticket the workspace is explicitly assigned to via the panel/banner (a
   * canonical "<KEY>-<NUMBER>" identifier), or `null` for none. This is the
   * user's own assertion of what the workspace is for, so it takes precedence
   * over the ticket inferred from the branch name.
   */
  assignedTicketId?: string | null;
};

/**
 * The ticket a workspace is assigned to from the signals carried on the
 * workspace itself: the explicit assignment when set, otherwise the ticket
 * parsed from the branch name. (PR links are matched separately — they live on
 * the issue, not the workspace.) The single source of truth for "this
 * workspace's ticket" without any network resolution.
 */
export const workspaceTicketId = (workspace: WorkspaceLink): string | null =>
  workspace.assignedTicketId ?? branchTicketId(workspace.branch);

/** Whether a workspace is working on a given issue (assigned ticket id or PR link). */
export const issueMatchesWorkspace = (issue: LinearIssue, workspace: WorkspaceLink): boolean => {
  if (workspaceTicketId(workspace) === issue.identifier) return true;
  if (workspace.pullRequestUrl === null) return false;
  return issue.attachments.some(
    (attachment) => isPullRequestAttachment(attachment) && attachment.url === workspace.pullRequestUrl,
  );
};

/** Every workspace associated with the issue, in the order given. */
export const workspacesForIssue = <T extends WorkspaceLink>(
  issue: LinearIssue,
  workspaces: ReadonlyArray<T>,
): ReadonlyArray<T> => workspaces.filter((workspace) => issueMatchesWorkspace(issue, workspace));
