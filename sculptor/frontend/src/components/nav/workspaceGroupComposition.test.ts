import { describe, expect, it } from "vitest";

import type { Workspace, WorkspaceGroup } from "~/api";

import { composeRepoSectionChildren } from "./workspaceGroupComposition.ts";

const makeWorkspace = (id: string, description: string, groupId?: string): Workspace =>
  ({ objectId: id, projectId: "p-alpha", description, groupId }) as unknown as Workspace;

const makeGroup = (id: string, name: string): WorkspaceGroup =>
  ({ objectId: id, projectId: "p-alpha", name, color: "blue" }) as unknown as WorkspaceGroup;

const idsOf = (workspaces: ReadonlyArray<Workspace>): Array<string> => workspaces.map((ws) => ws.objectId);

describe("composeRepoSectionChildren", () => {
  it("returns every workspace loose (same array) when there are no groups", () => {
    const workspaces = [makeWorkspace("w-b", "banana"), makeWorkspace("w-a", "apple")];
    const result = composeRepoSectionChildren(workspaces, []);
    expect(result.groupsWithMembers).toEqual([]);
    // Identity, not a copy: with the feature idle the loose list is exactly
    // the input, so downstream memoization sees a stable reference.
    expect(result.looseWorkspaces).toBe(workspaces);
  });

  it("partitions members out of the loose list, keeping the groups' given order", () => {
    const groups = [makeGroup("wsg-1", "Group 1"), makeGroup("wsg-2", "Group 2")];
    const workspaces = [
      makeWorkspace("w-a", "apple", "wsg-2"),
      makeWorkspace("w-b", "banana"),
      makeWorkspace("w-c", "cherry", "wsg-1"),
    ];
    const result = composeRepoSectionChildren(workspaces, groups);
    expect(result.groupsWithMembers.map(({ group }) => group.objectId)).toEqual(["wsg-1", "wsg-2"]);
    expect(idsOf(result.groupsWithMembers[0]?.members ?? [])).toEqual(["w-c"]);
    expect(idsOf(result.groupsWithMembers[1]?.members ?? [])).toEqual(["w-a"]);
    expect(idsOf(result.looseWorkspaces)).toEqual(["w-b"]);
  });

  it("sorts a group's members by description", () => {
    const groups = [makeGroup("wsg-1", "Group 1")];
    const workspaces = [
      makeWorkspace("w-c", "cherry", "wsg-1"),
      makeWorkspace("w-a", "apple", "wsg-1"),
      makeWorkspace("w-b", "banana", "wsg-1"),
    ];
    const result = composeRepoSectionChildren(workspaces, groups);
    expect(idsOf(result.groupsWithMembers[0]?.members ?? [])).toEqual(["w-a", "w-b", "w-c"]);
  });

  it("keeps the loose list's incoming (stored drag) order", () => {
    const groups = [makeGroup("wsg-1", "Group 1")];
    const workspaces = [
      makeWorkspace("w-c", "cherry"),
      makeWorkspace("w-m", "member", "wsg-1"),
      makeWorkspace("w-a", "apple"),
    ];
    const result = composeRepoSectionChildren(workspaces, groups);
    expect(idsOf(result.looseWorkspaces)).toEqual(["w-c", "w-a"]);
  });

  it("leaves a workspace loose when its groupId matches no live group", () => {
    const groups = [makeGroup("wsg-1", "Group 1")];
    const workspaces = [makeWorkspace("w-a", "apple", "wsg-dissolved"), makeWorkspace("w-b", "banana", "wsg-1")];
    const result = composeRepoSectionChildren(workspaces, groups);
    expect(idsOf(result.looseWorkspaces)).toEqual(["w-a"]);
    expect(idsOf(result.groupsWithMembers[0]?.members ?? [])).toEqual(["w-b"]);
  });

  it("drops a group no workspace claims (empty groups never render)", () => {
    const groups = [makeGroup("wsg-1", "Group 1"), makeGroup("wsg-empty", "Group 2")];
    const workspaces = [makeWorkspace("w-a", "apple", "wsg-1")];
    const result = composeRepoSectionChildren(workspaces, groups);
    expect(result.groupsWithMembers.map(({ group }) => group.objectId)).toEqual(["wsg-1"]);
  });
});
