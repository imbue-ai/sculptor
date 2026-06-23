import { describe, expect, it } from "vitest";

import type { LinearIssue } from "./client.ts";
import { mergeTickets } from "./sources.ts";

const issue = (identifier: string): LinearIssue => ({
  identifier,
  title: identifier,
  url: `https://linear.app/x/${identifier}`,
  description: null,
  priorityLabel: null,
  state: null,
  assignee: null,
  attachments: [],
  children: [],
});

describe("mergeTickets", () => {
  it("orders branch (primary) first, then PR-linked, then pinned", () => {
    const result = mergeTickets({ primary: issue("A"), prLinked: [issue("B")], pinned: [issue("C")] });
    expect(result.map((ticket) => ticket.issue.identifier)).toEqual(["A", "B", "C"]);
    expect(result[0]).toMatchObject({ isPrimary: true, sources: ["branch"] });
    expect(result[1]).toMatchObject({ isPrimary: false, sources: ["pr"] });
    expect(result[2]).toMatchObject({ isPrimary: false, sources: ["pinned"] });
  });

  it("de-duplicates an issue seen via several sources, unioning its sources and keeping primary", () => {
    const a = issue("A");
    const result = mergeTickets({ primary: a, prLinked: [a], pinned: [a] });
    expect(result).toHaveLength(1);
    expect(result[0].isPrimary).toBe(true);
    expect(result[0].sources).toEqual(["branch", "pr", "pinned"]);
  });

  it("works with no primary (e.g. branch has no linked issue)", () => {
    const result = mergeTickets({ primary: null, prLinked: [], pinned: [issue("C")] });
    expect(result.map((ticket) => ticket.issue.identifier)).toEqual(["C"]);
    expect(result[0]).toMatchObject({ isPrimary: false, sources: ["pinned"] });
  });

  it("keeps a pinned issue that is also the primary first and primary", () => {
    const a = issue("A");
    const result = mergeTickets({ primary: a, prLinked: [], pinned: [issue("B"), a] });
    expect(result.map((ticket) => ticket.issue.identifier)).toEqual(["A", "B"]);
    expect(result[0]).toMatchObject({ isPrimary: true, sources: ["branch", "pinned"] });
  });
});
