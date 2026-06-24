import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { PLUGIN_ID } from "../constants.ts";
import {
  fetchIssueByTicket,
  fetchIssuesForUrl,
  fetchPrimaryIssue,
  isPullRequestAttachment,
  type LinearIssue,
} from "./client.ts";
import { mergeTickets, type PanelTicket } from "./sources.ts";
import { parseTicket, type Ticket } from "./ticket.ts";

// Issues are cached on the host's shared QueryClient: they survive panel
// close/reopen and workspace switches, and concurrent mounts dedupe to one
// request. staleTime must be explicit — the host default is Infinity, tuned for
// its WebSocket-invalidated queries. The API key is deliberately never part of
// a key (keys are visible in cache inspection); the settings component
// invalidates this plugin's namespace when the key changes.
const STALE_TIME = 60_000;
const GC_TIME = 30 * 60_000;

export type LinearTickets = {
  tickets: ReadonlyArray<PanelTicket>;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
};

/**
 * Assembles the panel's ticket list from three sources — the branch's issue
 * (primary), the issues that issue's PR links to, and the user's pinned issues
 * — each cached independently and merged (de-duplicated) for display.
 */
export const useLinearTickets = (inputs: {
  apiKey: string;
  branch: string | null;
  pullRequestUrl: string | null;
  pinnedIds: ReadonlyArray<string>;
}): LinearTickets => {
  const { apiKey, branch, pullRequestUrl, pinnedIds } = inputs;

  // Primary: the branch's issue (authoritative branch link, then regex fallback,
  // then the workspace's PR — see fetchPrimaryIssue). The PR URL is part of the
  // key so the primary re-resolves once the workspace opens (or closes) a PR.
  const primaryQuery = useQuery({
    queryKey: [PLUGIN_ID, "primary", branch, pullRequestUrl],
    queryFn: ({ signal }) => {
      if (!branch) throw new Error("No workspace branch");
      return fetchPrimaryIssue({ apiKey, branch, ticketFallback: parseTicket(branch), pullRequestUrl, signal });
    },
    enabled: Boolean(apiKey && branch),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });
  const primary = primaryQuery.data ?? null;

  // PR-linked: issues Linear shows for the primary issue's PR attachment(s) —
  // "Linear's point of view" beyond what the branch name reveals.
  const prUrls = useMemo(
    () => (primary ? primary.attachments.filter(isPullRequestAttachment).map((attachment) => attachment.url) : []),
    [primary],
  );
  const primaryId = primary?.identifier;
  const prLinkedQuery = useQuery({
    queryKey: [PLUGIN_ID, "prLinked", primaryId, prUrls],
    queryFn: async ({ signal }) => {
      const lists = await Promise.all(prUrls.map((url) => fetchIssuesForUrl({ apiKey, url, signal })));
      const seen = new Set<string>(primaryId ? [primaryId] : []);
      const linked: Array<LinearIssue> = [];
      for (const issue of lists.flat()) {
        if (seen.has(issue.identifier)) continue;
        seen.add(issue.identifier);
        linked.push(issue);
      }
      return linked;
    },
    enabled: Boolean(apiKey && primaryId && prUrls.length > 0),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  // Pinned: user-chosen issues, fetched by identifier. Sorted so the key is
  // stable regardless of pin order.
  const sortedPinned = useMemo(() => [...pinnedIds].sort(), [pinnedIds]);
  const pinnedQuery = useQuery({
    queryKey: [PLUGIN_ID, "pinned", sortedPinned],
    queryFn: async ({ signal }) => {
      const tickets = sortedPinned.map(parseTicket).filter((ticket): ticket is Ticket => ticket !== null);
      const issues = await Promise.all(tickets.map((ticket) => fetchIssueByTicket({ apiKey, ticket, signal })));
      return issues.filter((issue): issue is LinearIssue => issue !== null);
    },
    enabled: Boolean(apiKey && sortedPinned.length > 0),
    staleTime: STALE_TIME,
    gcTime: GC_TIME,
    retry: 1,
  });

  const tickets = useMemo(
    () => mergeTickets({ primary, prLinked: prLinkedQuery.data ?? [], pinned: pinnedQuery.data ?? [] }),
    [primary, prLinkedQuery.data, pinnedQuery.data],
  );

  const refetch = (): void => {
    void primaryQuery.refetch();
    void prLinkedQuery.refetch();
    void pinnedQuery.refetch();
  };

  return {
    tickets,
    isFetching: primaryQuery.isFetching || prLinkedQuery.isFetching || pinnedQuery.isFetching,
    // The primary issue is the panel's main content, so surface its error.
    isError: primaryQuery.isError,
    error: primaryQuery.error,
    refetch,
  };
};
