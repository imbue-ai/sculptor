import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchAssignedIssues,
  fetchPrimaryIssue,
  isPullRequestAttachment,
  type LinearAttachment,
  normalizeIssue,
  prLabel,
} from "./client.ts";
import type { Ticket } from "./ticket.ts";

const attachment = (url: string): LinearAttachment => ({ url, sourceType: "github", title: null });

// A raw issue as Linear returns it, with connections still wrapped in `{ nodes }`.
// Typed loosely so a test can omit a connection to exercise the absent-field path.
const rawIssue = (overrides: Record<string, unknown> = {}): Parameters<typeof normalizeIssue>[0] =>
  ({
    identifier: "SCU-1",
    title: "Parent",
    url: "https://linear.app/x/issue/SCU-1",
    description: null,
    priorityLabel: null,
    state: null,
    assignee: null,
    attachments: { nodes: [] },
    children: { nodes: [] },
    ...overrides,
  }) as Parameters<typeof normalizeIssue>[0];

describe("normalizeIssue", () => {
  it("flattens sub-issues out of the children connection", () => {
    const child = {
      identifier: "SCU-2",
      title: "Child",
      url: "https://linear.app/x/issue/SCU-2",
      state: { name: "Todo", type: "unstarted", color: "#fff" },
    };
    expect(normalizeIssue(rawIssue({ children: { nodes: [child] } })).children).toEqual([child]);
  });

  it("defaults children to [] when the connection is absent", () => {
    expect(normalizeIssue(rawIssue({ children: undefined })).children).toEqual([]);
  });
});

describe("isPullRequestAttachment", () => {
  it("matches GitHub pull and GitLab merge-request URLs", () => {
    expect(isPullRequestAttachment(attachment("https://github.com/o/r/pull/74"))).toBe(true);
    expect(isPullRequestAttachment(attachment("https://gitlab.com/o/r/-/merge_requests/12"))).toBe(true);
  });

  it("rejects non-PR URLs", () => {
    expect(isPullRequestAttachment(attachment("https://github.com/o/r/commit/abc123"))).toBe(false);
    expect(isPullRequestAttachment(attachment("https://example.com/pulls"))).toBe(false);
  });
});

describe("fetchPrimaryIssue", () => {
  // A successful GraphQL HTTP response wrapping `data`.
  const gqlOk = (data: unknown): Partial<Response> => ({ ok: true, status: 200, json: async () => ({ data }) });

  // Stub global fetch with a handler that routes on the GraphQL query text, and
  // record the queries it saw so a test can assert which tiers were reached.
  const stubFetch = (route: (query: string) => unknown): Array<string> => {
    const queries: Array<string> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: { body: string }) => {
        const { query } = JSON.parse(init.body) as { query: string };
        queries.push(query);
        return route(query);
      }),
    );
    return queries;
  };

  const baseInputs = { apiKey: "k", signal: new AbortController().signal };
  const ticket = (identifier: string, key: string, number: number): Ticket => ({ identifier, key, number });

  afterEach(() => vi.unstubAllGlobals());

  it("returns the branch-linked issue and never reaches later tiers when issueVcsBranchSearch hits", async () => {
    const queries = stubFetch((query) =>
      query.includes("issueVcsBranchSearch")
        ? gqlOk({ issueVcsBranchSearch: rawIssue({ identifier: "SCU-10" }) })
        : null,
    );
    const issue = await fetchPrimaryIssue({
      ...baseInputs,
      branch: "anything",
      ticketFallback: ticket("SCU-20", "SCU", 20),
      pullRequestUrl: "https://github.com/o/r/pull/9",
    });
    expect(issue?.identifier).toBe("SCU-10");
    expect(queries).toHaveLength(1);
  });

  it("falls back to the workspace PR when both the branch link and the parsed identifier miss", async () => {
    const queries = stubFetch((query) => {
      if (query.includes("issueVcsBranchSearch")) return gqlOk({ issueVcsBranchSearch: null });
      if (query.includes("attachmentsForURL")) {
        return gqlOk({ attachmentsForURL: { nodes: [{ issue: rawIssue({ identifier: "SCU-99" }) }] } });
      }
      throw new Error(`unexpected query: ${query}`);
    });
    const issue = await fetchPrimaryIssue({
      ...baseInputs,
      // A Sculptor-generated branch: no Linear link, no identifier to parse.
      branch: "claude/some-feature-y03vlc",
      ticketFallback: null,
      pullRequestUrl: "https://github.com/o/r/pull/9",
    });
    expect(issue?.identifier).toBe("SCU-99");
    expect(queries.some((q) => q.includes("attachmentsForURL"))).toBe(true);
  });

  it("prefers the parsed identifier over the PR URL", async () => {
    const queries = stubFetch((query) => {
      if (query.includes("issueVcsBranchSearch")) return gqlOk({ issueVcsBranchSearch: null });
      if (query.includes("issues(filter")) return gqlOk({ issues: { nodes: [rawIssue({ identifier: "SCU-7" })] } });
      throw new Error(`should not reach the PR tier: ${query}`);
    });
    const issue = await fetchPrimaryIssue({
      ...baseInputs,
      branch: "dev/scu-7-thing",
      ticketFallback: ticket("SCU-7", "SCU", 7),
      pullRequestUrl: "https://github.com/o/r/pull/9",
    });
    expect(issue?.identifier).toBe("SCU-7");
    expect(queries.some((q) => q.includes("attachmentsForURL"))).toBe(false);
  });

  it("returns null without querying the PR when there is no workspace PR URL", async () => {
    const queries = stubFetch((query) =>
      query.includes("issueVcsBranchSearch") ? gqlOk({ issueVcsBranchSearch: null }) : null,
    );
    const issue = await fetchPrimaryIssue({
      ...baseInputs,
      branch: "claude/some-feature-y03vlc",
      ticketFallback: null,
      pullRequestUrl: null,
    });
    expect(issue).toBeNull();
    expect(queries).toHaveLength(1);
  });
});

describe("fetchAssignedIssues", () => {
  // Stub fetch with a fixed response, capturing each parsed request body so a
  // test can assert the query text and the variables it forwarded.
  const stub = (response: Partial<Response>): Array<{ query: string; variables: Record<string, unknown> }> => {
    const calls: Array<{ query: string; variables: Record<string, unknown> }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: { body: string }) => {
        calls.push(JSON.parse(init.body));
        return response;
      }),
    );
    return calls;
  };

  const inputs = { apiKey: "k", limit: 50, signal: new AbortController().signal };

  afterEach(() => vi.unstubAllGlobals());

  it("reads viewer.assignedIssues, forwards the limit, and normalizes the nodes", async () => {
    const calls = stub({
      ok: true,
      status: 200,
      json: async () => ({ data: { viewer: { assignedIssues: { nodes: [rawIssue({ identifier: "SCU-5" })] } } } }),
    });
    const issues = await fetchAssignedIssues(inputs);
    expect(issues.map((i) => i.identifier)).toEqual(["SCU-5"]);
    // Connections are flattened by normalizeIssue.
    expect(issues[0].attachments).toEqual([]);
    expect(calls[0].query).toContain("viewer");
    expect(calls[0].query).toContain("assignedIssues");
    expect(calls[0].variables).toEqual({ first: 50 });
  });

  it("rejects a bad API key (401) with an actionable message", async () => {
    stub({ ok: false, status: 401, json: async () => ({}) });
    await expect(fetchAssignedIssues(inputs)).rejects.toThrow("Linear rejected the API key");
  });

  it("surfaces a non-OK HTTP status", async () => {
    stub({ ok: false, status: 500, json: async () => ({}) });
    await expect(fetchAssignedIssues(inputs)).rejects.toThrow("HTTP 500");
  });

  it("surfaces a GraphQL error message", async () => {
    stub({ ok: true, status: 200, json: async () => ({ errors: [{ message: "Throttled" }] }) });
    await expect(fetchAssignedIssues(inputs)).rejects.toThrow("Throttled");
  });

  it("throws when the response carries neither data nor errors", async () => {
    stub({ ok: true, status: 200, json: async () => ({}) });
    await expect(fetchAssignedIssues(inputs)).rejects.toThrow("Linear returned no data");
  });
});

describe("prLabel", () => {
  it("labels GitHub pulls with #<n>", () => {
    expect(prLabel("https://github.com/o/r/pull/74")).toBe("#74");
  });

  it("labels GitLab merge requests with !<n>", () => {
    expect(prLabel("https://gitlab.com/o/r/-/merge_requests/12")).toBe("!12");
  });

  it("falls back to 'PR' when there is no number", () => {
    expect(prLabel("https://github.com/o/r")).toBe("PR");
  });

  it("keys the sigil off the matched route, not a substring of the whole URL", () => {
    // A GitHub pull whose query string mentions "/merge_requests/" must still
    // read as "#", not "!".
    expect(prLabel("https://github.com/o/r/pull/74?ref=/merge_requests/9")).toBe("#74");
  });
});
