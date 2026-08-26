import { describe, expect, it, vi } from "vitest";

import { groupCommands } from "../groupCommands.ts";
import type { Command } from "../types.ts";

const cmd = (overrides: Partial<Command> & Pick<Command, "id" | "title">): Command =>
  ({
    group: "navigation",
    perform: vi.fn(),
    ...overrides,
  }) as Command;

describe("groupCommands", () => {
  it("returns groups in the static group order", () => {
    const result = groupCommands(
      [
        cmd({ id: "n1", title: "Nav A", group: "navigation" }),
        cmd({ id: "h1", title: "Help A", group: "help" }),
        cmd({ id: "v1", title: "View A", group: "view" }),
      ],
      false,
    );
    expect(result.map((g) => g.id)).toEqual(["navigation", "view", "help"]);
  });

  it("alphabetizes commands within a group", () => {
    const result = groupCommands(
      [
        cmd({ id: "n1", title: "Beta", group: "navigation" }),
        cmd({ id: "n2", title: "Alpha", group: "navigation" }),
        cmd({ id: "n3", title: "Charlie", group: "navigation" }),
      ],
      false,
    );
    expect(result[0]?.commands.map((c) => c.title)).toEqual(["Alpha", "Beta", "Charlie"]);
  });

  it("places top-level commands before page-scoped ones within a group", () => {
    const result = groupCommands(
      [
        cmd({ id: "p1", title: "Sub Alpha", group: "navigation", onPage: "settings.section" }),
        cmd({ id: "r1", title: "Root Beta", group: "navigation" }),
        cmd({ id: "p2", title: "Sub Charlie", group: "navigation", onPage: "settings.section" }),
        cmd({ id: "r2", title: "Root Alpha", group: "navigation" }),
      ],
      false,
    );
    expect(result[0]?.commands.map((c) => c.id)).toEqual(["r2", "r1", "p1", "p2"]);
  });

  it("drops empty groups", () => {
    const result = groupCommands([cmd({ id: "n1", title: "Alpha", group: "navigation" })], false);
    expect(result.find((g) => g.id === "view")).toBeUndefined();
    expect(result.find((g) => g.id === "navigation")).not.toBeUndefined();
  });

  it("places primary commands before non-primary within the same scope", () => {
    // Even when alphabetical order would put the primary command later
    // (e.g. "New Workspace" after "Go to Home"), `primary` commands
    // must lead their tier so headliner page-openers and entry-points
    // sit at the top of their group.
    const result = groupCommands(
      [
        cmd({ id: "n1", title: "Go to Home", group: "navigation" }),
        cmd({ id: "n2", title: "Go to Settings", group: "navigation" }),
        cmd({ id: "n3", title: "New Workspace", group: "navigation", primary: true }),
        cmd({ id: "n4", title: "Open Settings", group: "navigation", primary: true }),
      ],
      false,
    );
    expect(result[0]?.commands.map((c) => c.id)).toEqual(["n3", "n4", "n1", "n2"]);
  });

  it("respects an explicit `order` field within scope+primary, ahead of alphabetical", () => {
    // Workspaces wants New, Open, Workspace actions, Switch agent,
    // Agent actions — that's N, O, W, S, A which alphabetical can't
    // express. `order` overrides alpha within the same scope+primary
    // tier.
    const result = groupCommands(
      [
        cmd({ id: "agent_act", title: "Agent actions...", group: "workspaces", primary: true, order: 50 }),
        cmd({ id: "switch_agent", title: "Switch agent...", group: "workspaces", primary: true, order: 40 }),
        cmd({ id: "ws_act", title: "Workspace actions...", group: "workspaces", primary: true, order: 30 }),
        cmd({ id: "open_ws", title: "Open Workspace...", group: "workspaces", primary: true, order: 20 }),
        cmd({ id: "new_ws", title: "New Workspace", group: "workspaces", primary: true, order: 10 }),
      ],
      false,
    );
    expect(result[0]?.commands.map((c) => c.id)).toEqual(["new_ws", "open_ws", "ws_act", "switch_agent", "agent_act"]);
  });

  it("during search, sorts groups by their best command score (descending)", () => {
    // Regression: typing a query that exact-matches a command in a
    // late-ordered group ("Dark" in the Theme group, id "view")
    // used to leave the earlier-ordered Workspaces group on top, so cmdk
    // auto-selected a weak subsequence match instead of the exact hit.
    // Sorting groups by their best score moves the merged view group
    // above Workspaces here.
    const scoreOf = (c: Command): number => {
      if (c.id === "dark") return 1000; // exact title match
      if (c.id === "delete") return 1.5; // weak subseq match
      return 0;
    };
    const result = groupCommands(
      [
        cmd({ id: "delete", title: "Delete workspace: bobathan's workspace", group: "workspaces" }),
        cmd({ id: "dark", title: "Dark", group: "view" }),
      ],
      true,
      scoreOf,
    );
    expect(result.map((g) => g.id)).toEqual(["view", "workspaces"]);
  });

  it("falls back to static groupOrder when there is no query (or no scorer)", () => {
    const result = groupCommands(
      [cmd({ id: "h1", title: "Help A", group: "help" }), cmd({ id: "n1", title: "Nav A", group: "navigation" })],
      false,
    );
    expect(result.map((g) => g.id)).toEqual(["navigation", "help"]);
  });
});
