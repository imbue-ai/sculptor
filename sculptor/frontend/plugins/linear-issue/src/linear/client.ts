import type { Ticket } from "./ticket.ts";

const LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql";

/** A link Linear holds against an issue (a PR, a design, a doc, …). */
export type LinearAttachment = { url: string; sourceType: string | null; title: string | null };

/** A Linear workflow state (e.g. "In Progress"), with its display color. */
export type LinearState = {
  name: string;
  type: string;
  color: string;
  /**
   * Linear's manual ordering of states within a team, used to sort states that
   * share a `type` (a team can have several "started" states). Optional because
   * not every fetch path selects it (e.g. sub-issue states don't need ordering).
   */
  position?: number;
};

/** A sub-issue, narrowed to what a ticket badge renders (id, title, status). */
export type LinearChild = {
  identifier: string;
  title: string;
  url: string;
  state: LinearState | null;
};

/** A Linear issue, narrowed to the fields the panel renders. */
export type LinearIssue = {
  identifier: string;
  title: string;
  url: string;
  description: string | null;
  priorityLabel: string | null;
  state: LinearState | null;
  assignee: { displayName: string } | null;
  attachments: ReadonlyArray<LinearAttachment>;
  /** Direct sub-issues, capped by the `children` selection in ISSUE_FIELDS. */
  children: ReadonlyArray<LinearChild>;
};

/** Lightweight issue shape for quick-search results. */
export type LinearIssueSummary = {
  identifier: string;
  title: string;
  state: { name: string; color: string } | null;
};

// Shared selection for a fully-rendered issue, so every fetch path (branch,
// identifier, PR-linked) returns the same shape. Sub-issues are fetched with a
// generous cap so the panel can show an accurate "+N more" beyond the first
// few it renders; a ticket with more children than this would undercount.
const CHILDREN_FETCH_LIMIT = 50;
const ISSUE_FIELDS = `
  identifier
  title
  url
  description
  priorityLabel
  state { name type color position }
  assignee { displayName }
  attachments { nodes { url sourceType title } }
  children(first: ${CHILDREN_FETCH_LIMIT}) { nodes { identifier title url state { name type color } } }
`;

type RawIssue = Omit<LinearIssue, "attachments" | "children"> & {
  attachments: { nodes: Array<LinearAttachment> };
  children: { nodes: Array<LinearChild> };
};

/** Flatten Linear's nested connections (`{ nodes }`) into the panel's flat shape. */
export const normalizeIssue = (raw: RawIssue): LinearIssue => ({
  identifier: raw.identifier,
  title: raw.title,
  url: raw.url,
  description: raw.description,
  priorityLabel: raw.priorityLabel,
  state: raw.state,
  assignee: raw.assignee,
  attachments: raw.attachments?.nodes ?? [],
  children: raw.children?.nodes ?? [],
});

// Single POST helper with shared auth + error handling. `signal` is the
// AbortSignal TanStack Query passes in, so superseded requests are cancelled.
const linearRequest = async <TData>(inputs: {
  apiKey: string;
  query: string;
  variables: Record<string, unknown>;
  signal: AbortSignal;
}): Promise<TData> => {
  const { apiKey, query, variables, signal } = inputs;
  const res = await fetch(LINEAR_GRAPHQL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: apiKey },
    body: JSON.stringify({ query, variables }),
    signal,
  });
  if (res.status === 400 || res.status === 401) {
    throw new Error("Linear rejected the API key — check it in plugin settings.");
  }
  if (!res.ok) {
    throw new Error(`Linear API error: HTTP ${res.status}`);
  }
  const json = (await res.json()) as { data?: TData; errors?: Array<{ message?: string }> };
  if (json.errors && json.errors.length > 0) {
    throw new Error(json.errors[0]?.message ?? "Linear GraphQL error");
  }
  if (!json.data) throw new Error("Linear returned no data");
  return json.data;
};

/** Look up a single issue by its "<KEY>-<NUMBER>" ticket. */
export const fetchIssueByTicket = async (inputs: {
  apiKey: string;
  ticket: Ticket;
  signal: AbortSignal;
}): Promise<LinearIssue | null> => {
  const { apiKey, ticket, signal } = inputs;
  const data = await linearRequest<{ issues: { nodes: Array<RawIssue> } }>({
    apiKey,
    query: `query ($key: String!, $num: Float!) {
      issues(filter: { team: { key: { eq: $key } }, number: { eq: $num } }, first: 1) { nodes { ${ISSUE_FIELDS} } }
    }`,
    variables: { key: ticket.key, num: ticket.number },
    signal,
  });
  const node = data.issues.nodes[0];
  return node ? normalizeIssue(node) : null;
};

/**
 * The workspace's issue, resolved through three tiers, cheapest/most
 * authoritative first:
 *
 *  1. `issueVcsBranchSearch` — Linear's own branch→issue link.
 *  2. an identifier parsed out of the branch name (e.g. `scu-1234`).
 *  3. the workspace's PR URL via `attachmentsForURL` — Sculptor-generated branch
 *     names carry no issue identifier and no Linear VCS link, but the workspace's
 *     PR does (Linear links it from the `[SCU-####]` PR title), and Linear
 *     resolves a PR URL to its issue authoritatively.
 *
 * Each tier is tried only when the previous one comes up empty.
 */
export const fetchPrimaryIssue = async (inputs: {
  apiKey: string;
  branch: string;
  ticketFallback: Ticket | null;
  pullRequestUrl: string | null;
  signal: AbortSignal;
}): Promise<LinearIssue | null> => {
  const { apiKey, branch, ticketFallback, pullRequestUrl, signal } = inputs;
  const data = await linearRequest<{ issueVcsBranchSearch: RawIssue | null }>({
    apiKey,
    query: `query ($branch: String!) { issueVcsBranchSearch(branchName: $branch) { ${ISSUE_FIELDS} } }`,
    variables: { branch },
    signal,
  });
  if (data.issueVcsBranchSearch) return normalizeIssue(data.issueVcsBranchSearch);
  if (ticketFallback) {
    const byTicket = await fetchIssueByTicket({ apiKey, ticket: ticketFallback, signal });
    if (byTicket) return byTicket;
  }
  if (pullRequestUrl) {
    const linked = await fetchIssuesForUrl({ apiKey, url: pullRequestUrl, signal });
    return linked[0] ?? null;
  }
  return null;
};

/** Issues a given URL (e.g. a PR) is linked to in Linear — Linear's view. */
export const fetchIssuesForUrl = async (inputs: {
  apiKey: string;
  url: string;
  signal: AbortSignal;
}): Promise<Array<LinearIssue>> => {
  const { apiKey, url, signal } = inputs;
  const data = await linearRequest<{ attachmentsForURL: { nodes: Array<{ issue: RawIssue | null }> } }>({
    apiKey,
    query: `query ($url: String!) { attachmentsForURL(url: $url, first: 25) { nodes { issue { ${ISSUE_FIELDS} } } } }`,
    variables: { url },
    signal,
  });
  return data.attachmentsForURL.nodes
    .map((node) => node.issue)
    .filter((issue): issue is RawIssue => issue !== null)
    .map(normalizeIssue);
};

/**
 * The current user's assigned issues, most-recently-updated first. Resolved
 * through the API key's `viewer`, so "me" is whoever the key belongs to. The
 * board caps the count and orders by `updatedAt` rather than filtering by state
 * so that recently-finished work stays visible (a just-completed ticket is the
 * most recently updated), while long-closed issues fall off the end.
 */
export const fetchAssignedIssues = async (inputs: {
  apiKey: string;
  limit: number;
  signal: AbortSignal;
}): Promise<Array<LinearIssue>> => {
  const { apiKey, limit, signal } = inputs;
  const data = await linearRequest<{ viewer: { assignedIssues: { nodes: Array<RawIssue> } } }>({
    apiKey,
    query: `query ($first: Int!) {
      viewer { assignedIssues(first: $first, orderBy: updatedAt) { nodes { ${ISSUE_FIELDS} } } }
    }`,
    variables: { first: limit },
    signal,
  });
  return data.viewer.assignedIssues.nodes.map(normalizeIssue);
};

/** Free-text issue search for the quick-search bar (`issueSearch` is deprecated). */
export const searchIssues = async (inputs: {
  apiKey: string;
  term: string;
  signal: AbortSignal;
}): Promise<Array<LinearIssueSummary>> => {
  const { apiKey, term, signal } = inputs;
  const data = await linearRequest<{ searchIssues: { nodes: Array<LinearIssueSummary> } }>({
    apiKey,
    query: `query ($term: String!) { searchIssues(term: $term, first: 8) { nodes { identifier title state { name color } } } }`,
    variables: { term },
    signal,
  });
  return data.searchIssues.nodes;
};

/** Whether an attachment points at a code-host pull/merge request. */
export const isPullRequestAttachment = (attachment: LinearAttachment): boolean =>
  /\/(pull|merge_requests)\//.test(attachment.url);

/** Short label for a PR/MR URL: "#74" for a GitHub pull, "!74" for a GitLab MR. */
export const prLabel = (url: string): string => {
  const match = url.match(/\/(pull|merge_requests)\/(\d+)/);
  if (!match) return "PR";
  // Key the sigil off the matched route segment, not a substring scan of the
  // whole URL — a query string or fragment could otherwise contain
  // "/merge_requests/" and mislabel a GitHub pull as a GitLab MR.
  return `${match[1] === "merge_requests" ? "!" : "#"}${match[2]}`;
};
