import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { Workspace, WorkspaceGroup } from "../../../api";
import {
  getWorkspaceGroupSyncVersion,
  resetWorkspaceGroupSyncVersionsForTesting,
  updateWorkspaceGroupsAtom,
  workspaceGroupAtomFamily,
  workspaceGroupIdsAtom,
  workspaceGroupMembersAtomFamily,
  workspaceGroupsArrayAtom,
  workspaceGroupsForProjectAtomFamily,
} from "./workspaceGroups.ts";
import { workspaceAtomFamily, workspaceIdsAtom } from "./workspaces.ts";

const makeGroup = (id: string, projectId: string, overrides: Partial<WorkspaceGroup> = {}): WorkspaceGroup => ({
  objectId: id,
  organizationReference: "org-1",
  projectId,
  name: `Group ${id}`,
  color: "blue",
  createdViaCli: false,
  isDeleted: false,
  createdAt: "2026-01-01T00:00:00Z",
  ...overrides,
});

const makeWorkspace = (id: string, projectId: string, groupId: string | null): Workspace =>
  ({ objectId: id, projectId, groupId, isDeleted: false }) as unknown as Workspace;

const seedWorkspaces = (store: ReturnType<typeof createStore>, workspaces: ReadonlyArray<Workspace>): void => {
  for (const workspace of workspaces) {
    store.set(workspaceAtomFamily(workspace.objectId), workspace);
  }
  store.set(
    workspaceIdsAtom,
    workspaces.map((workspace) => workspace.objectId),
  );
};

beforeEach(() => {
  // Sync versions live in a module-level map, so they leak across tests
  // without an explicit reset.
  resetWorkspaceGroupSyncVersionsForTesting();
});

describe("updateWorkspaceGroupsAtom", () => {
  it("is undefined until the first frame, then loaded — even when the frame is empty", () => {
    const store = createStore();
    expect(store.get(workspaceGroupsArrayAtom)).toBeUndefined();

    store.set(updateWorkspaceGroupsAtom, []);

    expect(store.get(workspaceGroupsArrayAtom)).toEqual([]);
    expect(store.get(workspaceGroupIdsAtom)).toEqual([]);
  });

  it("stores delivered groups and exposes them through the array atom", () => {
    const store = createStore();
    const groupA = makeGroup("wsg-a", "p-1");
    const groupB = makeGroup("wsg-b", "p-2");

    store.set(updateWorkspaceGroupsAtom, [groupA, groupB]);

    expect(store.get(workspaceGroupAtomFamily("wsg-a"))).toEqual(groupA);
    expect(store.get(workspaceGroupsArrayAtom)).toHaveLength(2);
  });

  it("merges delta frames: a later frame adds without dropping existing groups", () => {
    const store = createStore();
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1")]);

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-b", "p-1")]);

    expect(store.get(workspaceGroupsArrayAtom)?.map((group) => group.objectId)).toEqual(
      expect.arrayContaining(["wsg-a", "wsg-b"]),
    );
  });

  it("applies field changes from a delta frame", () => {
    const store = createStore();
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1", { name: "Group 1" })]);

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1", { name: "Renamed", color: "teal" })]);

    const group = store.get(workspaceGroupAtomFamily("wsg-a"));
    expect(group?.name).toBe("Renamed");
    expect(group?.color).toBe("teal");
  });

  it("keeps the stored object reference when a frame carries an unchanged group", () => {
    const store = createStore();
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1")]);
    const before = store.get(workspaceGroupAtomFamily("wsg-a"));

    // Stream frames always carry fresh objects; an unconditional write would
    // re-render every subscriber per frame.
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1")]);

    expect(store.get(workspaceGroupAtomFamily("wsg-a"))).toBe(before);
  });

  it("removes a deleted group from the list and nulls its atom", () => {
    const store = createStore();
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1"), makeGroup("wsg-b", "p-1")]);

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1", { isDeleted: true })]);

    expect(store.get(workspaceGroupAtomFamily("wsg-a"))).toBeNull();
    expect(store.get(workspaceGroupsArrayAtom)?.map((group) => group.objectId)).toEqual(["wsg-b"]);
  });

  it("bumps the sync version for every delivered group, including unchanged and deleted ones", () => {
    const store = createStore();
    expect(getWorkspaceGroupSyncVersion("wsg-a")).toBe(0);

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1")]);
    expect(getWorkspaceGroupSyncVersion("wsg-a")).toBe(1);

    // Unchanged content still bumps: the frame is authoritative, so a failed
    // mutation's rollback must yield to it.
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1")]);
    expect(getWorkspaceGroupSyncVersion("wsg-a")).toBe(2);

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1", { isDeleted: true })]);
    expect(getWorkspaceGroupSyncVersion("wsg-a")).toBe(3);
  });
});

describe("workspaceGroupsForProjectAtomFamily", () => {
  it("returns only the project's groups, in creation order", () => {
    const store = createStore();
    store.set(updateWorkspaceGroupsAtom, [
      makeGroup("wsg-late", "p-1", { createdAt: "2026-01-03T00:00:00Z" }),
      makeGroup("wsg-early", "p-1", { createdAt: "2026-01-01T00:00:00Z" }),
      makeGroup("wsg-other", "p-2"),
    ]);

    const groups = store.get(workspaceGroupsForProjectAtomFamily("p-1"));
    expect(groups.map((group) => group.objectId)).toEqual(["wsg-early", "wsg-late"]);
  });

  it("is an empty list before the first frame and for unknown projects", () => {
    const store = createStore();
    expect(store.get(workspaceGroupsForProjectAtomFamily("p-1"))).toEqual([]);

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1")]);
    expect(store.get(workspaceGroupsForProjectAtomFamily("p-unknown"))).toEqual([]);
  });

  it("keeps its array reference when another project's groups change", () => {
    const store = createStore();
    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-a", "p-1"), makeGroup("wsg-b", "p-2")]);
    const before = store.get(workspaceGroupsForProjectAtomFamily("p-1"));

    store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-b", "p-2", { name: "Renamed" })]);

    expect(store.get(workspaceGroupsForProjectAtomFamily("p-1"))).toBe(before);
  });
});

describe("workspaceGroupMembersAtomFamily", () => {
  it("joins member workspaces by their groupId", () => {
    const store = createStore();
    seedWorkspaces(store, [
      makeWorkspace("ws-1", "p-1", "wsg-a"),
      makeWorkspace("ws-2", "p-1", "wsg-a"),
      makeWorkspace("ws-3", "p-1", "wsg-b"),
      makeWorkspace("ws-4", "p-1", null),
    ]);

    const members = store.get(workspaceGroupMembersAtomFamily("wsg-a"));
    expect(members.map((workspace) => workspace.objectId)).toEqual(["ws-1", "ws-2"]);
  });

  it("is empty for a group with no members delivered yet", () => {
    const store = createStore();
    expect(store.get(workspaceGroupMembersAtomFamily("wsg-a"))).toEqual([]);
  });

  it("keeps its array reference when a non-member workspace changes", () => {
    const store = createStore();
    const member = makeWorkspace("ws-1", "p-1", "wsg-a");
    const loose = makeWorkspace("ws-2", "p-1", null);
    seedWorkspaces(store, [member, loose]);
    const before = store.get(workspaceGroupMembersAtomFamily("wsg-a"));

    store.set(workspaceAtomFamily("ws-2"), { ...loose, description: "changed" } as unknown as Workspace);

    expect(store.get(workspaceGroupMembersAtomFamily("wsg-a"))).toBe(before);
  });

  it("reflects a membership change on the workspace", () => {
    const store = createStore();
    const workspace = makeWorkspace("ws-1", "p-1", "wsg-a");
    seedWorkspaces(store, [workspace]);
    expect(store.get(workspaceGroupMembersAtomFamily("wsg-a"))).toHaveLength(1);

    store.set(workspaceAtomFamily("ws-1"), { ...workspace, groupId: null } as unknown as Workspace);

    expect(store.get(workspaceGroupMembersAtomFamily("wsg-a"))).toEqual([]);
  });
});
