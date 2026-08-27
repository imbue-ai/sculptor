import { describe, expect, it } from "vitest";

import { branchTicketId, issueMatchesWorkspace, workspacesForIssue, workspaceTicketId } from "./association.ts";
import type { LinearAttachment, LinearIssue } from "./client.ts";

const issue = (identifier: string, attachments: ReadonlyArray<LinearAttachment> = []): LinearIssue => ({
  identifier,
  title: identifier,
  url: `https://linear.app/x/${identifier}`,
  description: null,
  priorityLabel: null,
  state: null,
  assignee: null,
  attachments,
  children: [],
});

const pr = (url: string): LinearAttachment => ({ url, sourceType: "github", title: null });

describe("branchTicketId", () => {
  it("extracts the canonical identifier from a Sculptor branch name", () => {
    expect(branchTicketId("dev/scu-1495-example")).toBe("SCU-1495");
  });

  it("returns null for branches with no ticket and for a null branch", () => {
    expect(branchTicketId("dev/just-a-title")).toBeNull();
    expect(branchTicketId(null)).toBeNull();
  });
});

describe("issueMatchesWorkspace", () => {
  it("matches when the branch carries the ticket identifier", () => {
    expect(issueMatchesWorkspace(issue("SCU-1495"), { branch: "dev/scu-1495-x", pullRequestUrl: null })).toBe(true);
  });

  it("does not match a different ticket on the branch", () => {
    expect(issueMatchesWorkspace(issue("SCU-1495"), { branch: "dev/scu-2000-x", pullRequestUrl: null })).toBe(false);
  });

  it("matches when the workspace PR is one of the issue's linked PRs", () => {
    const url = "https://github.com/imbue-ai/sculptor/pull/210";
    expect(issueMatchesWorkspace(issue("SCU-1", [pr(url)]), { branch: "feature", pullRequestUrl: url })).toBe(true);
  });

  it("does not match a non-PR attachment that happens to share the URL", () => {
    const url = "https://linear.app/x/doc";
    const design: LinearAttachment = { url, sourceType: "figma", title: null };
    expect(issueMatchesWorkspace(issue("SCU-1", [design]), { branch: "feature", pullRequestUrl: url })).toBe(false);
  });

  it("does not match on PR when the workspace has no PR", () => {
    const url = "https://github.com/imbue-ai/sculptor/pull/210";
    expect(issueMatchesWorkspace(issue("SCU-1", [pr(url)]), { branch: "feature", pullRequestUrl: null })).toBe(false);
  });

  it("matches an explicit assignment even when the branch carries no ticket", () => {
    expect(
      issueMatchesWorkspace(issue("SCU-1495"), {
        branch: "dev/just-a-title",
        pullRequestUrl: null,
        assignedTicketId: "SCU-1495",
      }),
    ).toBe(true);
  });

  it("lets the explicit assignment win over the branch ticket", () => {
    // Branch points at SCU-2000 but the user assigned SCU-1495: the workspace is
    // the one for SCU-1495 and not for SCU-2000.
    const workspace = { branch: "dev/scu-2000-x", pullRequestUrl: null, assignedTicketId: "SCU-1495" };
    expect(issueMatchesWorkspace(issue("SCU-1495"), workspace)).toBe(true);
    expect(issueMatchesWorkspace(issue("SCU-2000"), workspace)).toBe(false);
  });
});

describe("workspaceTicketId", () => {
  it("returns the explicit assignment when set, ignoring the branch", () => {
    expect(workspaceTicketId({ branch: "dev/scu-2000-x", pullRequestUrl: null, assignedTicketId: "SCU-1495" })).toBe(
      "SCU-1495",
    );
  });

  it("falls back to the branch ticket when there is no assignment", () => {
    expect(workspaceTicketId({ branch: "dev/scu-2000-x", pullRequestUrl: null })).toBe("SCU-2000");
  });

  it("is null when neither an assignment nor a branch ticket is present", () => {
    expect(workspaceTicketId({ branch: "dev/just-a-title", pullRequestUrl: null, assignedTicketId: null })).toBeNull();
  });
});

describe("workspacesForIssue", () => {
  it("returns only the associated workspaces, preserving order", () => {
    const ws = [
      { id: "a", branch: "dev/scu-1495-x", pullRequestUrl: null },
      { id: "b", branch: "dev/other", pullRequestUrl: null },
      { id: "c", branch: "dev/scu-1495-y", pullRequestUrl: null },
    ];
    expect(workspacesForIssue(issue("SCU-1495"), ws).map((w) => w.id)).toEqual(["a", "c"]);
  });
});
