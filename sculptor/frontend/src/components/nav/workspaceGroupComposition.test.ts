import { describe, expect, it } from "vitest";

import type { Workspace, WorkspaceGroup } from "~/api";

import type { RepoSectionChild } from "./workspaceGroupComposition.ts";
import { composeRepoSectionChildren, repoSectionChildKey } from "./workspaceGroupComposition.ts";

const makeWorkspace = (id: string, description: string, groupId?: string): Workspace =>
  ({ objectId: id, projectId: "p-alpha", description, groupId }) as unknown as Workspace;

const makeGroup = (id: string, name: string): WorkspaceGroup =>
  ({ objectId: id, projectId: "p-alpha", name, color: "blue" }) as unknown as WorkspaceGroup;

const keysOf = (children: ReadonlyArray<RepoSectionChild>): Array<string> => children.map(repoSectionChildKey);

const membersOf = (children: ReadonlyArray<RepoSectionChild>, groupId: string): Array<string> => {
  const child = children.find((candidate) => candidate.kind === "group" && candidate.group.objectId === groupId);
  return child?.kind === "group" ? child.members.map((member) => member.objectId) : [];
};

describe("composeRepoSectionChildren", () => {
  it("returns every workspace loose, alphabetically, when there are no groups", () => {
    const workspaces = [makeWorkspace("w-b", "banana"), makeWorkspace("w-a", "apple")];
    const children = composeRepoSectionChildren(workspaces, [], undefined, undefined);
    expect(keysOf(children)).toEqual(["w-a", "w-b"]);
    expect(children.every((child) => child.kind === "workspace")).toBe(true);
  });

  it("interleaves group cards and loose workspaces alphabetically by display name", () => {
    const groups = [makeGroup("wsg-1", "banana group")];
    const workspaces = [
      makeWorkspace("w-c", "cherry"),
      makeWorkspace("w-a", "apple"),
      makeWorkspace("w-m", "member", "wsg-1"),
    ];
    const children = composeRepoSectionChildren(workspaces, groups, undefined, undefined);
    expect(keysOf(children)).toEqual(["w-a", "wsg-1", "w-c"]);
  });

  it("renders the stored mixed lane first (workspace and group ids together), then the rest alphabetically", () => {
    const groups = [makeGroup("wsg-1", "a group")];
    const workspaces = [
      makeWorkspace("w-a", "apple"),
      makeWorkspace("w-b", "banana"),
      makeWorkspace("w-c", "cherry"),
      makeWorkspace("w-m", "member", "wsg-1"),
    ];
    const children = composeRepoSectionChildren(workspaces, groups, ["w-c", "wsg-1"], undefined);
    // Stored: cherry, then the card; unstored apple/banana follow alphabetically.
    expect(keysOf(children)).toEqual(["w-c", "wsg-1", "w-a", "w-b"]);
  });

  it("keeps an old snapshot's workspace-only lane valid alongside groups", () => {
    // A lane persisted before workspace groups existed contains only ws ids;
    // the card simply joins the unstored tail at its alphabetical slot.
    const groups = [makeGroup("wsg-1", "zebra group")];
    const workspaces = [
      makeWorkspace("w-a", "apple"),
      makeWorkspace("w-b", "banana"),
      makeWorkspace("w-m", "member", "wsg-1"),
    ];
    const children = composeRepoSectionChildren(workspaces, groups, ["w-b", "w-a"], undefined);
    expect(keysOf(children)).toEqual(["w-b", "w-a", "wsg-1"]);
  });

  it("skips stored ids that resolve to nothing (deleted workspaces, hidden groups)", () => {
    // With no groups given (the flag off), a stored group id must be skipped
    // exactly like a deleted workspace id — the lane degrades to a plain
    // workspace order.
    const workspaces = [makeWorkspace("w-a", "apple"), makeWorkspace("w-b", "banana")];
    const children = composeRepoSectionChildren(workspaces, [], ["wsg-gone", "w-b", "w-deleted"], undefined);
    expect(keysOf(children)).toEqual(["w-b", "w-a"]);
  });

  it("sorts a group's members by description by default", () => {
    const groups = [makeGroup("wsg-1", "Group 1")];
    const workspaces = [
      makeWorkspace("w-c", "cherry", "wsg-1"),
      makeWorkspace("w-a", "apple", "wsg-1"),
      makeWorkspace("w-b", "banana", "wsg-1"),
    ];
    const children = composeRepoSectionChildren(workspaces, groups, undefined, undefined);
    expect(membersOf(children, "wsg-1")).toEqual(["w-a", "w-b", "w-c"]);
  });

  it("renders a group's stored member order first, then unstored members alphabetically", () => {
    const groups = [makeGroup("wsg-1", "Group 1")];
    const workspaces = [
      makeWorkspace("w-a", "apple", "wsg-1"),
      makeWorkspace("w-b", "banana", "wsg-1"),
      makeWorkspace("w-c", "cherry", "wsg-1"),
    ];
    const children = composeRepoSectionChildren(workspaces, groups, undefined, {
      "wsg-1": ["w-c", "w-stale", "w-b"],
    });
    expect(membersOf(children, "wsg-1")).toEqual(["w-c", "w-b", "w-a"]);
  });

  it("leaves a workspace loose when its groupId matches no live group", () => {
    const groups = [makeGroup("wsg-1", "Group 1")];
    const workspaces = [makeWorkspace("w-a", "apple", "wsg-dissolved"), makeWorkspace("w-b", "banana", "wsg-1")];
    const children = composeRepoSectionChildren(workspaces, groups, undefined, undefined);
    expect(keysOf(children)).toEqual(["w-a", "wsg-1"]);
    expect(membersOf(children, "wsg-1")).toEqual(["w-b"]);
  });

  it("drops a group no workspace claims (empty groups never render)", () => {
    const groups = [makeGroup("wsg-1", "Group 1"), makeGroup("wsg-empty", "Group 2")];
    const workspaces = [makeWorkspace("w-a", "apple", "wsg-1")];
    const children = composeRepoSectionChildren(workspaces, groups, undefined, undefined);
    expect(keysOf(children)).toEqual(["wsg-1"]);
  });
});
