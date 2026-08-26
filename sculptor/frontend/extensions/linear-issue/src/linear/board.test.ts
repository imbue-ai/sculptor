import { describe, expect, it } from "vitest";

import { buildBoard } from "./board.ts";
import type { LinearIssue, LinearState } from "./client.ts";

const state = (name: string, type: string, position = 0): LinearState => ({
  name,
  type,
  color: "#000",
  position,
});

const issue = (identifier: string, s: LinearState | null): LinearIssue => ({
  identifier,
  title: identifier,
  url: `https://linear.app/x/${identifier}`,
  description: null,
  priorityLabel: null,
  state: s,
  assignee: null,
  attachments: [],
  children: [],
});

type Ws = { id: string; branch: string | null; pullRequestUrl: string | null };
const ws = (id: string, branch: string): Ws => ({ id, branch, pullRequestUrl: null });

describe("buildBoard", () => {
  it("orders groups active-first, then by within-type position", () => {
    const groups = buildBoard(
      [
        issue("A", state("Done", "completed")),
        issue("B", state("Backlog", "backlog")),
        issue("C", state("In Progress", "started", 2)),
        issue("D", state("In Review", "started", 1)),
        issue("E", state("Todo", "unstarted")),
      ],
      [],
    );
    expect(groups.map((g) => g.stateName)).toEqual(["In Review", "In Progress", "Todo", "Backlog", "Done"]);
  });

  it("orders same-type groups deterministically by name when positions tie (cross-team)", () => {
    // Two teams can each have a same-type state with the same `position`; the
    // board must still order them stably rather than by input/Map order.
    const groups = buildBoard([issue("A", state("Zeta", "started", 1)), issue("B", state("Alpha", "started", 1))], []);
    expect(groups.map((g) => g.stateName)).toEqual(["Alpha", "Zeta"]);
  });

  it("keeps rows in input order within a group", () => {
    const s = state("In Progress", "started");
    const groups = buildBoard([issue("A", s), issue("B", s)], []);
    expect(groups).toHaveLength(1);
    expect(groups[0].rows.map((r) => r.issue.identifier)).toEqual(["A", "B"]);
  });

  it("attaches associated workspaces to each row", () => {
    const groups = buildBoard([issue("SCU-1495", state("In Progress", "started"))], [ws("w1", "dev/scu-1495-x")]);
    expect(groups[0].rows[0].workspaces.map((w) => w.id)).toEqual(["w1"]);
  });

  it("attaches a workspace via its explicit assignment even when the branch doesn't match", () => {
    const workspace = { id: "w1", branch: "dev/no-ticket", pullRequestUrl: null, assignedTicketId: "SCU-1495" };
    const groups = buildBoard([issue("SCU-1495", state("In Progress", "started"))], [workspace]);
    expect(groups[0].rows[0].workspaces.map((w) => w.id)).toEqual(["w1"]);
  });

  it("leaves rows with no workspace empty rather than dropping them", () => {
    const groups = buildBoard([issue("SCU-9", state("Todo", "unstarted"))], [ws("w1", "dev/scu-1-x")]);
    expect(groups[0].rows[0].workspaces).toEqual([]);
  });

  it("caps terminal-state groups and reports the overflow", () => {
    const done = state("Done", "completed");
    const issues = Array.from({ length: 12 }, (_, i) => issue(`D-${i}`, done));
    const groups = buildBoard(issues, []);
    expect(groups[0].rows).toHaveLength(8);
    expect(groups[0].hiddenCount).toBe(4);
  });

  it("does not cap active-state groups", () => {
    const started = state("In Progress", "started");
    const issues = Array.from({ length: 12 }, (_, i) => issue(`S-${i}`, started));
    const groups = buildBoard(issues, []);
    expect(groups[0].rows).toHaveLength(12);
    expect(groups[0].hiddenCount).toBe(0);
  });

  it("groups issues with no state under a trailing 'No status' bucket", () => {
    const groups = buildBoard([issue("A", null), issue("B", state("In Progress", "started"))], []);
    expect(groups.map((g) => g.stateName)).toEqual(["In Progress", "No status"]);
  });
});
