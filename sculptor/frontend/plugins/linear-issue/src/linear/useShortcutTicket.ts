import { useQuery } from "@tanstack/react-query";

import { PLUGIN_ID } from "../constants.ts";
import { fetchIssueByTicket, fetchPrimaryIssue, type LinearIssue } from "./client.ts";
import { parseTicket } from "./ticket.ts";

// Same cache tuning as the panel's queries (see useLinearTickets.ts): explicit
// staleTime because the host default is Infinity.
const STALE_TIME = 60_000;
const GC_TIME = 30 * 60_000;

export type ShortcutTicket = {
  issue: LinearIssue | null;
  /** True when showing the branch ticket because no explicit shortcut is set. */
  isDefault: boolean;
  isFetching: boolean;
};

/**
 * Resolves the single issue the banner widget shows: the explicitly-assigned
 * shortcut when set, otherwise the branch's primary issue. The default path
 * reuses the panel's `["primary", branch, pullRequestUrl]` query key, so an open
 * panel and the widget dedupe to one request and always agree on the branch
 * ticket — which means `pullRequestUrl` must be passed identically here.
 */
export const useShortcutTicket = (inputs: {
  apiKey: string;
  branch: string | null;
  pullRequestUrl: string | null;
  shortcutId: string | null;
}): ShortcutTicket => {
  const { apiKey, branch, pullRequestUrl, shortcutId } = inputs;

  const primaryQuery = useQuery({
    queryKey: [PLUGIN_ID, "primary", branch, pullRequestUrl],
    queryFn: ({ signal }) => {
      if (!branch) throw new Error("No workspace branch");
      return fetchPrimaryIssue({ apiKey, branch, ticketFallback: parseTicket(branch), pullRequestUrl, signal });
    },
    enabled: Boolean(apiKey && branch && !shortcutId),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  const overrideQuery = useQuery({
    queryKey: [PLUGIN_ID, "issue", shortcutId],
    queryFn: ({ signal }) => {
      const ticket = parseTicket(shortcutId);
      if (!ticket) return null;
      return fetchIssueByTicket({ apiKey, ticket, signal });
    },
    enabled: Boolean(apiKey && shortcutId),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  if (shortcutId) {
    return { issue: overrideQuery.data ?? null, isDefault: false, isFetching: overrideQuery.isFetching };
  }
  return { issue: primaryQuery.data ?? null, isDefault: true, isFetching: primaryQuery.isFetching };
};
