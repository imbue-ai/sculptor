import type { Ticket } from "./ticket.ts";

const LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql";

/** A link Linear holds against an issue (a PR, a design, a doc, …). */
export type LinearAttachment = { url: string; sourceType: string | null; title: string | null };

/** A Linear issue, narrowed to the fields the panel renders. */
export type LinearIssue = {
  identifier: string;
  title: string;
  url: string;
  description: string | null;
  priorityLabel: string | null;
  state: { name: string; type: string; color: string } | null;
  assignee: { displayName: string } | null;
  attachments: ReadonlyArray<LinearAttachment>;
};

/** Lightweight issue shape for quick-search results. */
export type LinearIssueSummary = {
  identifier: string;
  title: string;
  state: { name: string; color: string } | null;
};

// Shared selection for a fully-rendered issue, so every fetch path (branch,
// identifier, PR-linked) returns the same shape.
const ISSUE_FIELDS = `
  identifier
  title
  url
  description
  priorityLabel
  state { name type color }
  assignee { displayName }
  attachments { nodes { url sourceType title } }
`;

type RawIssue = Omit<LinearIssue, "attachments"> & { attachments: { nodes: Array<LinearAttachment> } };

const normalizeIssue = (raw: RawIssue): LinearIssue => ({
  identifier: raw.identifier,
  title: raw.title,
  url: raw.url,
  description: raw.description,
  priorityLabel: raw.priorityLabel,
  state: raw.state,
  assignee: raw.assignee,
  attachments: raw.attachments?.nodes ?? [],
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
 * The workspace's issue. Asks Linear which issue is linked to this VCS branch
 * (authoritative — Linear's own link), falling back to parsing an identifier
 * out of the branch name when Linear has no link yet.
 */
export const fetchPrimaryIssue = async (inputs: {
  apiKey: string;
  branch: string;
  ticketFallback: Ticket | null;
  signal: AbortSignal;
}): Promise<LinearIssue | null> => {
  const { apiKey, branch, ticketFallback, signal } = inputs;
  const data = await linearRequest<{ issueVcsBranchSearch: RawIssue | null }>({
    apiKey,
    query: `query ($branch: String!) { issueVcsBranchSearch(branchName: $branch) { ${ISSUE_FIELDS} } }`,
    variables: { branch },
    signal,
  });
  if (data.issueVcsBranchSearch) return normalizeIssue(data.issueVcsBranchSearch);
  if (ticketFallback) return fetchIssueByTicket({ apiKey, ticket: ticketFallback, signal });
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
