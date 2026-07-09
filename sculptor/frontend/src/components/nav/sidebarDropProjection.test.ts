import { describe, expect, it } from "vitest";

import type { Workspace, WorkspaceGroup } from "~/api";

import type { SectionProjection, SectionRowProjection } from "./sidebarDropProjection.ts";
import {
  applySectionProjection,
  flatSectionItemIds,
  locateWorkspaceParent,
  projectSectionDrop,
  toggleBoundaryDepth,
} from "./sidebarDropProjection.ts";
import type { RepoSectionChild } from "./workspaceGroupComposition.ts";
import { repoSectionChildKey } from "./workspaceGroupComposition.ts";

const makeWorkspace = (id: string, groupId?: string): Workspace =>
  ({ objectId: id, projectId: "p-alpha", description: id, groupId }) as unknown as Workspace;

const makeGroup = (id: string): WorkspaceGroup =>
  ({ objectId: id, projectId: "p-alpha", name: id, color: "blue" }) as unknown as WorkspaceGroup;

const loose = (id: string): RepoSectionChild => ({ kind: "workspace", workspace: makeWorkspace(id) });

const group = (id: string, memberIds: ReadonlyArray<string>): RepoSectionChild => ({
  kind: "group",
  group: makeGroup(id),
  members: memberIds.map((memberId) => makeWorkspace(memberId, id)),
});

const NONE = new Set<string>();

const keysOf = (children: ReadonlyArray<RepoSectionChild>): Array<string> => children.map(repoSectionChildKey);

const membersOf = (children: ReadonlyArray<RepoSectionChild>, groupId: string): Array<string> => {
  const child = children.find((candidate) => candidate.kind === "group" && candidate.group.objectId === groupId);
  return child?.kind === "group" ? child.members.map((member) => member.objectId) : [];
};

// The canonical fixture: [apple, Group1(m1, m2), banana, Group2(n1)].
const CHILDREN: ReadonlyArray<RepoSectionChild> = [
  loose("w-apple"),
  group("wsg-1", ["w-m1", "w-m2"]),
  loose("w-banana"),
  group("wsg-2", ["w-n1"]),
];

const project = (
  activeId: string,
  overId: string,
  opts: {
    depthIntent?: "inside" | "outside";
    collapsed?: ReadonlySet<string>;
    children?: ReadonlyArray<RepoSectionChild>;
  } = {},
): SectionProjection | null =>
  projectSectionDrop({
    children: opts.children ?? CHILDREN,
    collapsedGroupIds: opts.collapsed ?? NONE,
    activeId,
    overId,
    depthIntent: opts.depthIntent ?? "inside",
  });

describe("flatSectionItemIds", () => {
  it("flattens loose rows, headers, and member rows in visible order", () => {
    expect(flatSectionItemIds(CHILDREN, NONE)).toEqual([
      "w-apple",
      "wsg-1",
      "w-m1",
      "w-m2",
      "w-banana",
      "wsg-2",
      "w-n1",
    ]);
  });

  it("collapsed groups contribute only their header", () => {
    expect(flatSectionItemIds(CHILDREN, new Set(["wsg-1"]))).toEqual(["w-apple", "wsg-1", "w-banana", "wsg-2", "w-n1"]);
  });

  it("a dragging group's members collapse into the drag", () => {
    expect(flatSectionItemIds(CHILDREN, NONE, "wsg-1")).toEqual(["w-apple", "wsg-1", "w-banana", "wsg-2", "w-n1"]);
  });
});

describe("locateWorkspaceParent", () => {
  it("finds a member's group and reports loose rows as null", () => {
    expect(locateWorkspaceParent(CHILDREN, "w-m2")).toBe("wsg-1");
    expect(locateWorkspaceParent(CHILDREN, "w-apple")).toBeNull();
    expect(locateWorkspaceParent(CHILDREN, "w-unknown")).toBeNull();
  });
});

describe("projectSectionDrop — loose row moves", () => {
  it("reorders within the loose lane", () => {
    // apple over banana: takes banana's slot below the group run.
    expect(project("w-apple", "w-banana")).toEqual({
      kind: "row",
      activeId: "w-apple",
      parentGroupId: null,
      index: 2,
      isBoundary: false,
    });
  });

  it("joins a group at its head when dropped on the slot under the header", () => {
    // banana dragged up onto m1: lands between header and m1 → member index 0.
    // The head slot is a boundary — it doubles as loose-before-the-group.
    expect(project("w-banana", "w-m1")).toEqual({
      kind: "row",
      activeId: "w-banana",
      parentGroupId: "wsg-1",
      index: 0,
      isBoundary: true,
    });
  });

  it("joins a group mid-run when dropped between two members", () => {
    // banana dragged up onto m2 (its slot is between m1 and m2).
    expect(project("w-banana", "w-m2")).toEqual({
      kind: "row",
      activeId: "w-banana",
      parentGroupId: "wsg-1",
      index: 1,
      isBoundary: false,
    });
  });

  it("dropping on an expanded header from above slots in at member index 0", () => {
    // apple over the header: apple takes the header's flat slot, pushing the
    // header up — apple sits between header and m1.
    expect(project("w-apple", "wsg-1")).toEqual({
      kind: "row",
      activeId: "w-apple",
      parentGroupId: "wsg-1",
      index: 0,
      isBoundary: true,
    });
  });

  it("the slot after a group's last member is a boundary and defaults inside", () => {
    // apple dragged down onto m2: coming from above, it lands AFTER m2 — the
    // group's tail, which is the ambiguous slot (REQ-DND-6).
    expect(project("w-apple", "w-m2")).toEqual({
      kind: "row",
      activeId: "w-apple",
      parentGroupId: "wsg-1",
      index: 2,
      isBoundary: true,
    });
  });

  it("the outside intent flips the tail boundary to loose-right-after-the-group", () => {
    const projection = project("w-apple", "w-m2", { depthIntent: "outside" });
    expect(projection).toEqual({
      kind: "row",
      activeId: "w-apple",
      parentGroupId: null,
      index: 1,
      isBoundary: true,
    });
    const next = applySectionProjection(CHILDREN, projection as SectionProjection);
    expect(keysOf(next)).toEqual(["wsg-1", "w-apple", "w-banana", "wsg-2"]);
  });
});

describe("projectSectionDrop — member row moves", () => {
  it("reorders members within their group", () => {
    expect(project("w-m1", "w-m2")).toEqual({
      kind: "row",
      activeId: "w-m1",
      parentGroupId: "wsg-1",
      index: 1,
      isBoundary: true,
    });
  });

  it("releases a member dragged up above its group's header", () => {
    // m1 over apple: lands above the header → loose at apple's slot.
    expect(project("w-m1", "w-apple")).toEqual({
      kind: "row",
      activeId: "w-m1",
      parentGroupId: null,
      index: 0,
      isBoundary: false,
    });
  });

  it("releases a member dragged down onto a loose row", () => {
    // m2 over banana: moving down lands after banana — directly below a loose
    // row → loose.
    expect(project("w-m2", "w-banana")).toEqual({
      kind: "row",
      activeId: "w-m2",
      parentGroupId: null,
      index: 3,
      isBoundary: false,
    });
  });

  it("moves a member into another group (group→group)", () => {
    // m1 dragged down onto n1 lands after it — inside wsg-2 at its tail.
    expect(project("w-m1", "w-n1")).toEqual({
      kind: "row",
      activeId: "w-m1",
      parentGroupId: "wsg-2",
      index: 1,
      isBoundary: true,
    });
  });

  it("the tail slot of the member's own group is a boundary that the outside intent flips loose", () => {
    expect(project("w-m1", "w-m2", { depthIntent: "outside" })).toEqual({
      kind: "row",
      activeId: "w-m1",
      parentGroupId: null,
      index: 2,
      isBoundary: true,
    });
  });

  it("a group's only member dragged to its own tail boundary can release (dissolve path)", () => {
    // n1 over wsg-2's header: n1 takes the header's slot… from below the
    // header, n1 ends directly ABOVE the header → loose before the group.
    expect(project("w-n1", "wsg-2")).toEqual({
      kind: "row",
      activeId: "w-n1",
      parentGroupId: null,
      index: 3,
      isBoundary: false,
    });
  });
});

describe("projectSectionDrop — depth intent scope", () => {
  it("the outside intent flips the head slot to loose-right-before-the-group", () => {
    // The gap between a group and whatever precedes it IS the head slot; with
    // the pointer outside the box the drop stays loose, before the group.
    const projection = project("w-banana", "w-m1", { depthIntent: "outside" });
    expect(projection).toEqual({
      kind: "row",
      activeId: "w-banana",
      parentGroupId: null,
      index: 1,
      isBoundary: true,
    });
    const next = applySectionProjection(CHILDREN, projection as SectionProjection);
    expect(keysOf(next)).toEqual(["w-apple", "w-banana", "wsg-1", "wsg-2"]);
  });

  it("loose slots are never boundaries", () => {
    const projection = project("w-apple", "w-banana", { depthIntent: "outside" });
    expect(projection).toEqual({
      kind: "row",
      activeId: "w-apple",
      parentGroupId: null,
      index: 2,
      isBoundary: false,
    });
  });
});

describe("projectSectionDrop — collapsed groups", () => {
  it("dropping onto a collapsed header appends to the group", () => {
    expect(project("w-apple", "wsg-1", { collapsed: new Set(["wsg-1"]) })).toEqual({
      kind: "append-collapsed",
      activeId: "w-apple",
      parentGroupId: "wsg-1",
    });
  });

  it("the slot below a collapsed header is loose, not inside", () => {
    // n1 dragged up onto banana lands directly below wsg-1's collapsed header;
    // with no member run on screen that slot is loose, not a silent join.
    const collapsed = new Set(["wsg-1"]);
    expect(project("w-n1", "w-banana", { collapsed })).toEqual({
      kind: "row",
      activeId: "w-n1",
      parentGroupId: null,
      index: 2,
      isBoundary: false,
    });
  });
});

describe("projectSectionDrop — group header drags", () => {
  it("reorders a group among the top-level children", () => {
    expect(project("wsg-1", "w-banana")).toEqual({ kind: "group", activeId: "wsg-1", index: 2 });
  });

  it("an over inside another group resolves to that group's top-level slot (no nesting)", () => {
    expect(project("wsg-1", "w-n1")).toEqual({ kind: "group", activeId: "wsg-1", index: 3 });
  });

  it("no-ops when the group targets its own slot (or its own member)", () => {
    expect(project("wsg-1", "wsg-1")).toBeNull();
    expect(project("wsg-1", "w-m1")).toBeNull();
  });
});

describe("projectSectionDrop — degenerate inputs", () => {
  it("returns null for unknown ids and self-targets", () => {
    expect(project("w-apple", "w-apple")).toBeNull();
    expect(project("w-ghost", "w-banana")).toBeNull();
    expect(project("w-apple", "w-ghost")).toBeNull();
  });
});

describe("toggleBoundaryDepth", () => {
  it("flips a group's last member out to loose-right-after-the-group", () => {
    const projection = toggleBoundaryDepth(CHILDREN, NONE, "w-m2", "outside", null);
    expect(projection).toEqual({
      kind: "row",
      activeId: "w-m2",
      parentGroupId: null,
      index: 2,
      isBoundary: true,
    });
    const next = applySectionProjection(CHILDREN, projection as SectionProjection);
    expect(keysOf(next)).toEqual(["w-apple", "wsg-1", "w-m2", "w-banana", "wsg-2"]);
  });

  it("flips a loose row sitting directly after an expanded group into its tail", () => {
    // banana sits directly after wsg-1 in the fixture.
    const projection = toggleBoundaryDepth(CHILDREN, NONE, "w-banana", "inside", null);
    expect(projection).toEqual({
      kind: "row",
      activeId: "w-banana",
      parentGroupId: "wsg-1",
      index: 2,
      isBoundary: true,
    });
  });

  it("resolves a pending same-parent tail projection's group for the outside flip", () => {
    // m1 previewed at its own group's tail (not yet applied): flipping outside
    // must target wsg-1's after-slot even though m1's display position is index 0.
    const pending: SectionRowProjection = {
      kind: "row",
      activeId: "w-m1",
      parentGroupId: "wsg-1",
      index: 1,
      isBoundary: true,
    };
    expect(toggleBoundaryDepth(CHILDREN, NONE, "w-m1", "outside", pending)).toEqual({
      kind: "row",
      activeId: "w-m1",
      parentGroupId: null,
      index: 2,
      isBoundary: true,
    });
  });

  it("accounts for a loose active row above the group when computing the after-slot", () => {
    // apple (loose, above wsg-1) previewed at wsg-1's tail: removing apple
    // shifts the group up one, so the loose after-slot is index 1, not 2.
    const pending: SectionRowProjection = {
      kind: "row",
      activeId: "w-apple",
      parentGroupId: "wsg-1",
      index: 2,
      isBoundary: true,
    };
    expect(toggleBoundaryDepth(CHILDREN, NONE, "w-apple", "outside", pending)).toEqual({
      kind: "row",
      activeId: "w-apple",
      parentGroupId: null,
      index: 1,
      isBoundary: true,
    });
  });

  it("returns null when the active row is not at a flippable boundary", () => {
    // m1 is not its group's last member; apple is not directly after a group.
    expect(toggleBoundaryDepth(CHILDREN, NONE, "w-m1", "outside", null)).toBeNull();
    expect(toggleBoundaryDepth(CHILDREN, NONE, "w-apple", "inside", null)).toBeNull();
  });

  it("does not flip into a collapsed group (the slot after it is simply loose)", () => {
    expect(toggleBoundaryDepth(CHILDREN, new Set(["wsg-1"]), "w-banana", "inside", null)).toBeNull();
  });
});

describe("applySectionProjection", () => {
  it("moves a loose row within the top-level lane", () => {
    const next = applySectionProjection(CHILDREN, project("w-apple", "w-banana") as SectionProjection);
    expect(keysOf(next)).toEqual(["wsg-1", "w-banana", "w-apple", "wsg-2"]);
  });

  it("moves a loose row into a group at the projected index", () => {
    const next = applySectionProjection(CHILDREN, project("w-banana", "w-m1") as SectionProjection);
    expect(keysOf(next)).toEqual(["w-apple", "wsg-1", "wsg-2"]);
    expect(membersOf(next, "wsg-1")).toEqual(["w-banana", "w-m1", "w-m2"]);
  });

  it("releases a member to the projected loose slot", () => {
    const next = applySectionProjection(CHILDREN, project("w-m2", "w-banana") as SectionProjection);
    expect(keysOf(next)).toEqual(["w-apple", "wsg-1", "w-banana", "w-m2", "wsg-2"]);
    expect(membersOf(next, "wsg-1")).toEqual(["w-m1"]);
  });

  it("moves a member between groups", () => {
    const next = applySectionProjection(CHILDREN, project("w-m1", "w-n1") as SectionProjection);
    expect(membersOf(next, "wsg-1")).toEqual(["w-m2"]);
    expect(membersOf(next, "wsg-2")).toEqual(["w-n1", "w-m1"]);
  });

  it("keeps an emptied group in the tree as a drop-back target", () => {
    const next = applySectionProjection(CHILDREN, project("w-n1", "w-apple") as SectionProjection);
    expect(keysOf(next)).toEqual(["w-n1", "w-apple", "wsg-1", "w-banana", "wsg-2"]);
    expect(membersOf(next, "wsg-2")).toEqual([]);
  });

  it("appends to a collapsed group without disturbing sibling order", () => {
    const projection = project("w-apple", "wsg-1", { collapsed: new Set(["wsg-1"]) }) as SectionProjection;
    const next = applySectionProjection(CHILDREN, projection);
    expect(keysOf(next)).toEqual(["wsg-1", "w-banana", "wsg-2"]);
    expect(membersOf(next, "wsg-1")).toEqual(["w-m1", "w-m2", "w-apple"]);
  });

  it("moves a whole group by its header", () => {
    const next = applySectionProjection(CHILDREN, project("wsg-1", "w-banana") as SectionProjection);
    expect(keysOf(next)).toEqual(["w-apple", "w-banana", "wsg-1", "wsg-2"]);
    expect(membersOf(next, "wsg-1")).toEqual(["w-m1", "w-m2"]);
  });

  it("returns the original children when the projection no longer resolves", () => {
    const stale: SectionProjection = {
      kind: "row",
      activeId: "w-ghost",
      parentGroupId: null,
      index: 0,
      isBoundary: false,
    };
    expect(applySectionProjection(CHILDREN, stale)).toBe(CHILDREN);
  });

  it("composes across successive applications (drag through several slots)", () => {
    // banana → into wsg-1 head → out above apple → back to loose tail.
    let display = CHILDREN;
    display = applySectionProjection(display, project("w-banana", "w-m1", { children: display }) as SectionProjection);
    expect(membersOf(display, "wsg-1")).toEqual(["w-banana", "w-m1", "w-m2"]);
    display = applySectionProjection(
      display,
      project("w-banana", "w-apple", { children: display }) as SectionProjection,
    );
    expect(keysOf(display)).toEqual(["w-banana", "w-apple", "wsg-1", "wsg-2"]);
    expect(membersOf(display, "wsg-1")).toEqual(["w-m1", "w-m2"]);
  });
});
