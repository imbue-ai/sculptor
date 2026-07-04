import { useQuery } from "@tanstack/react-query";

import { PLUGIN_ID } from "../constants.ts";
import { fetchIssueByTicket, fetchPrimaryIssue, type LinearIssue } from "./client.ts";
import { parseTicket } from "./ticket.ts";

// Same cache tuning as the panel's queries (see useLinearTickets.ts): explicit
// staleTime because the host default is Infinity.
const STALE_TIME = 60_000;
const GC_TIME = 30 * 60_000;

export type WorkspaceTicketIssue = {
  issue: LinearIssue | null;
  /** True when showing the branch ticket because there is no explicit assignment. */
  isDefault: boolean;
  isFetching: boolean;
};

/**
 * Resolves the single issue the banner widget shows: the explicitly-assigned
 * ticket when set, otherwise the branch's primary issue. The default path reuses
 * the panel's `["primary", branch, pullRequestUrl]` query key, so an open panel
 * and the widget dedupe to one request and always agree on the branch ticket —
 * which means `pullRequestUrl` must be passed identically here.
 */
export const useWorkspaceTicketIssue = (inputs: {
  apiKey: string;
  branch: string | null;
  pullRequestUrl: string | null;
  assignedTicketId: string | null;
}): WorkspaceTicketIssue => {
  const { apiKey, branch, pullRequestUrl, assignedTicketId } = inputs;

  const primaryQuery = useQuery({
    queryKey: [PLUGIN_ID, "primary", branch, pullRequestUrl],
    queryFn: ({ signal }) => {
      if (!branch) throw new Error("No workspace branch");
      return fetchPrimaryIssue({ apiKey, branch, ticketFallback: parseTicket(branch), pullRequestUrl, signal });
    },
    enabled: Boolean(apiKey && branch && !assignedTicketId),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  const assignedQuery = useQuery({
    queryKey: [PLUGIN_ID, "issue", assignedTicketId],
    queryFn: ({ signal }) => {
      const ticket = parseTicket(assignedTicketId);
      if (!ticket) return null;
      return fetchIssueByTicket({ apiKey, ticket, signal });
    },
    enabled: Boolean(apiKey && assignedTicketId),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  if (assignedTicketId) {
    return { issue: assignedQuery.data ?? null, isDefault: false, isFetching: assignedQuery.isFetching };
  }
  return { issue: primaryQuery.data ?? null, isDefault: true, isFetching: primaryQuery.isFetching };
};
