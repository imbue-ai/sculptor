import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { Project, UserConfig, Workspace, WorkspaceGroup } from "~/api";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { updateWorkspaceGroupsAtom } from "~/common/state/atoms/workspaceGroups.ts";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";
import { layoutPersistenceAdapter } from "~/components/sections/persistence/LocalStorageLayoutAdapter.ts";
import { globalLayoutAtom } from "~/components/sections/sectionAtoms.ts";

import type { SectionProjection } from "./sidebarDropProjection.ts";
import { applySectionProjection, projectSectionDrop } from "./sidebarDropProjection.ts";
import {
  commitSectionDropAtom,
  groupWorkspacesByRepo,
  reorderSidebarRepoGroupAtom,
  restoreSectionOrderAtom,
  sidebarOrderedWorkspacesAtom,
  sidebarRepoGroupsAtom,
} from "./sidebarWorkspaceOrder.ts";
import type { RepoSectionChild } from "./workspaceGroupComposition.ts";
import { repoSectionChildKey } from "./workspaceGroupComposition.ts";

const makeWorkspace = (id: string, projectId: string, description: string, groupId?: string): Workspace =>
  ({ objectId: id, projectId, description, groupId }) as unknown as Workspace;

const makeProject = (id: string, name: string): Project => ({ objectId: id, name }) as unknown as Project;

const makeGroup = (id: string, projectId: string, name: string): WorkspaceGroup =>
  ({ objectId: id, projectId, name, color: "blue", isDeleted: false }) as unknown as WorkspaceGroup;

const PROJECTS = [makeProject("p-alpha", "alpha"), makeProject("p-beta", "beta")];
const WORKSPACES = [
  makeWorkspace("w-apple", "p-alpha", "apple"),
  makeWorkspace("w-banana", "p-alpha", "banana"),
  makeWorkspace("w-cherry", "p-alpha", "cherry"),
  makeWorkspace("w-dates", "p-beta", "dates"),
];

const workspaceIdsOf = (groups: ReturnType<typeof groupWorkspacesByRepo>, projectId: string): Array<string> =>
  groups.find((group) => group.projectId === projectId)?.workspaces.map((ws) => ws.objectId) ?? [];

const childKeysOf = (groups: ReturnType<typeof groupWorkspacesByRepo>, projectId: string): Array<string> =>
  groups.find((group) => group.projectId === projectId)?.children.map(repoSectionChildKey) ?? [];

const memberIdsOf = (
  groups: ReturnType<typeof groupWorkspacesByRepo>,
  projectId: string,
  groupId: string,
): Array<string> => {
  const child = groups
    .find((group) => group.projectId === projectId)
    ?.children.find((candidate) => candidate.kind === "group" && candidate.group.objectId === groupId);
  return child?.kind === "group" ? child.members.map((member) => member.objectId) : [];
};

describe("groupWorkspacesByRepo", () => {
  it("defaults to alphabetical groups and workspaces without a stored order", () => {
    const groups = groupWorkspacesByRepo(WORKSPACES, PROJECTS);
    expect(groups.map((group) => group.projectId)).toEqual(["p-alpha", "p-beta"]);
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-apple", "w-banana", "w-cherry"]);
  });

  it("renders stored workspace positions first, then unstored ones alphabetically", () => {
    const groups = groupWorkspacesByRepo(WORKSPACES, PROJECTS, {
      repos: [],
      // banana was dragged above cherry; apple has no stored position.
      workspaces: { "p-alpha": ["w-banana", "w-cherry"] },
    });
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-banana", "w-cherry", "w-apple"]);
  });

  it("skips stored ids that no longer resolve to a workspace", () => {
    const groups = groupWorkspacesByRepo(WORKSPACES, PROJECTS, {
      repos: [],
      workspaces: { "p-alpha": ["w-deleted", "w-cherry", "w-apple"] },
    });
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-cherry", "w-apple", "w-banana"]);
  });

  it("renders an id stored twice only once, at its first stored slot", () => {
    const groups = groupWorkspacesByRepo(WORKSPACES, PROJECTS, {
      repos: [],
      workspaces: { "p-alpha": ["w-cherry", "w-banana", "w-cherry"] },
    });
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-cherry", "w-banana", "w-apple"]);
  });

  it("renders stored repo positions first, then unstored repos alphabetically", () => {
    const projects = [...PROJECTS, makeProject("p-gamma", "gamma")];
    const workspaces = [...WORKSPACES, makeWorkspace("w-elder", "p-gamma", "elder")];
    const groups = groupWorkspacesByRepo(workspaces, projects, {
      repos: ["p-gamma", "p-deleted"],
      workspaces: {},
    });
    expect(groups.map((group) => group.projectId)).toEqual(["p-gamma", "p-alpha", "p-beta"]);
  });

  it("interleaves workspace-group cards into the mixed lane and flattens members in place", () => {
    const workspaces = [
      makeWorkspace("w-apple", "p-alpha", "apple"),
      makeWorkspace("w-zebra", "p-alpha", "zebra"),
      makeWorkspace("w-member", "p-alpha", "member", "wsg-1"),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS, undefined, [
      makeGroup("wsg-1", "p-alpha", "middle group"),
    ]);
    // Alphabetical interleave: apple < "middle group" < zebra.
    expect(childKeysOf(groups, "p-alpha")).toEqual(["w-apple", "wsg-1", "w-zebra"]);
    // The flattened order expands the card's members at the card's position.
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-apple", "w-member", "w-zebra"]);
  });

  it("keeps an old workspace-only stored lane valid when groups are present", () => {
    const workspaces = [...WORKSPACES, makeWorkspace("w-member", "p-alpha", "member", "wsg-1")];
    const groups = groupWorkspacesByRepo(
      workspaces,
      PROJECTS,
      // A lane persisted before groups existed: workspace ids only.
      { repos: [], workspaces: { "p-alpha": ["w-cherry", "w-apple"] } },
      [makeGroup("wsg-1", "p-alpha", "zzz group")],
    );
    expect(childKeysOf(groups, "p-alpha")).toEqual(["w-cherry", "w-apple", "w-banana", "wsg-1"]);
  });
});

const seedStore = (store: ReturnType<typeof createStore>, workspaces: ReadonlyArray<Workspace> = WORKSPACES): void => {
  for (const project of PROJECTS) {
    store.set(projectAtomFamily(project.objectId), project);
  }
  store.set(
    projectIdsAtom,
    PROJECTS.map((project) => project.objectId),
  );
  for (const workspace of workspaces) {
    store.set(workspaceAtomFamily(workspace.objectId), workspace);
  }
  store.set(
    workspaceIdsAtom,
    workspaces.map((workspace) => workspace.objectId),
  );
};

// Seed a store where p-alpha has the "Group 1" card (members cherry + elder)
// plus the loose apple/banana rows, with the workspace-groups flag on.
const seedGroupedStore = (store: ReturnType<typeof createStore>): void => {
  seedStore(store, [
    makeWorkspace("w-apple", "p-alpha", "apple"),
    makeWorkspace("w-banana", "p-alpha", "banana"),
    makeWorkspace("w-cherry", "p-alpha", "cherry", "wsg-1"),
    makeWorkspace("w-elder", "p-alpha", "elder", "wsg-1"),
    makeWorkspace("w-dates", "p-beta", "dates"),
  ]);
  store.set(userConfigAtom, { enableWorkspaceGroups: true } as unknown as UserConfig);
  store.set(updateWorkspaceGroupsAtom, [makeGroup("wsg-1", "p-alpha", "Group 1")]);
};

// The children a store currently composes for a project — the tree a drag
// starts from, exactly what SidebarRepoGroup hands the projection module.
const childrenOf = (store: ReturnType<typeof createStore>, projectId: string): ReadonlyArray<RepoSectionChild> =>
  store.get(sidebarRepoGroupsAtom).find((group) => group.projectId === projectId)?.children ?? [];

// Project a drop the way the drag layer does and return the resulting tree.
const projectedChildren = (
  store: ReturnType<typeof createStore>,
  projectId: string,
  activeId: string,
  overId: string,
  depthIntent: "inside" | "outside" = "inside",
): ReadonlyArray<RepoSectionChild> => {
  const children = childrenOf(store, projectId);
  const projection = projectSectionDrop({
    children,
    collapsedGroupIds: new Set<string>(),
    activeId,
    overId,
    depthIntent,
  }) as SectionProjection;
  return applySectionProjection(children, projection);
};

describe("sidebar drop-commit atoms", () => {
  it("stores the full mixed lane a loose reorder lands", () => {
    const store = createStore();
    seedStore(store);

    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-cherry", "w-apple"),
    });

    expect(workspaceIdsOf(store.get(sidebarRepoGroupsAtom), "p-alpha")).toEqual(["w-cherry", "w-apple", "w-banana"]);
    // The full visible order is materialized, so later fallback merging is exact.
    expect(store.get(globalLayoutAtom).sidebarOrder.workspaces["p-alpha"]).toEqual(["w-cherry", "w-apple", "w-banana"]);
  });

  it("keeps keyboard cycling's flattened order in lockstep with the rendered groups", () => {
    const store = createStore();
    seedStore(store);

    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-apple", "w-cherry"),
    });

    const flattened = store.get(sidebarRepoGroupsAtom).flatMap((group) => group.workspaces);
    expect(store.get(sidebarOrderedWorkspacesAtom)).toEqual(flattened);
    expect(flattened.map((workspace) => workspace.objectId)).toEqual(["w-banana", "w-cherry", "w-apple", "w-dates"]);
  });

  it("moves a repo group to the drop slot and stores the full group order", () => {
    const store = createStore();
    seedStore(store);

    store.set(reorderSidebarRepoGroupAtom, { activeProjectId: "p-beta", overProjectId: "p-alpha" });

    expect(store.get(sidebarRepoGroupsAtom).map((group) => group.projectId)).toEqual(["p-beta", "p-alpha"]);
    expect(store.get(globalLayoutAtom).sidebarOrder.repos).toEqual(["p-beta", "p-alpha"]);
  });

  it("persists the committed order through the layout adapter", () => {
    const store = createStore();
    seedStore(store);

    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-banana", "w-apple"),
    });

    // globalLayoutAtom writes through the adapter (read-your-writes even inside
    // the debounce window), so the custom order survives the next app start.
    const persisted = layoutPersistenceAdapter.read({ kind: "global" });
    expect(persisted?.sidebarOrder.workspaces["p-alpha"]).toEqual(["w-banana", "w-apple", "w-cherry"]);
  });

  it("ignores repo-group drops whose ids don't resolve", () => {
    const store = createStore();
    seedStore(store);
    const before = store.get(globalLayoutAtom);

    store.set(reorderSidebarRepoGroupAtom, { activeProjectId: "p-unknown", overProjectId: "p-alpha" });

    expect(store.get(globalLayoutAtom)).toBe(before);
  });

  it("moves a whole group within the mixed lane and stores workspace and group ids together", () => {
    const store = createStore();
    seedGroupedStore(store);

    // Default lane: apple, banana, Group 1. Drag the group header to the top.
    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "wsg-1", "w-apple"),
    });

    expect(childKeysOf(store.get(sidebarRepoGroupsAtom), "p-alpha")).toEqual(["wsg-1", "w-apple", "w-banana"]);
    expect(store.get(globalLayoutAtom).sidebarOrder.workspaces["p-alpha"]).toEqual(["wsg-1", "w-apple", "w-banana"]);
  });

  it("reorders members within a group and stores the member lane", () => {
    const store = createStore();
    seedGroupedStore(store);

    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-elder", "w-cherry"),
    });

    expect(memberIdsOf(store.get(sidebarRepoGroupsAtom), "p-alpha", "wsg-1")).toEqual(["w-elder", "w-cherry"]);
    expect(store.get(globalLayoutAtom).sidebarOrder.groupMembers?.["wsg-1"]).toEqual(["w-elder", "w-cherry"]);
  });

  it("persists the member lane through the layout adapter", () => {
    const store = createStore();
    seedGroupedStore(store);

    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-elder", "w-cherry"),
    });

    const persisted = layoutPersistenceAdapter.read({ kind: "global" });
    expect(persisted?.sidebarOrder.groupMembers?.["wsg-1"]).toEqual(["w-elder", "w-cherry"]);
  });

  it("writes both lanes for a membership-changing drop (loose row into a group)", () => {
    const store = createStore();
    seedGroupedStore(store);

    // banana dragged down onto cherry lands right after it, inside the group.
    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-banana", "w-cherry"),
    });

    const order = store.get(globalLayoutAtom).sidebarOrder;
    expect(order.workspaces["p-alpha"]).toEqual(["w-apple", "wsg-1"]);
    expect(order.groupMembers?.["wsg-1"]).toEqual(["w-cherry", "w-banana", "w-elder"]);
  });

  it("restores exactly the lanes a rejected drop overwrote, including never-stored ones", () => {
    const store = createStore();
    seedGroupedStore(store);

    // No lanes stored yet: the snapshot must remember "never stored", not [].
    const snapshot = store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-banana", "w-cherry"),
    });
    expect(store.get(globalLayoutAtom).sidebarOrder.workspaces["p-alpha"]).toEqual(["w-apple", "wsg-1"]);

    store.set(restoreSectionOrderAtom, snapshot);

    const order = store.get(globalLayoutAtom).sidebarOrder;
    expect(order.workspaces["p-alpha"]).toBeUndefined();
    expect(order.groupMembers?.["wsg-1"]).toBeUndefined();
  });

  it("restores the previous stored lanes when they existed", () => {
    const store = createStore();
    seedGroupedStore(store);
    // A first drop stores lanes...
    store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-elder", "w-cherry"),
    });

    // ...a second drop overwrites them and then fails.
    const snapshot = store.set(commitSectionDropAtom, {
      projectId: "p-alpha",
      children: projectedChildren(store, "p-alpha", "w-banana", "w-apple"),
    });
    store.set(restoreSectionOrderAtom, snapshot);

    const order = store.get(globalLayoutAtom).sidebarOrder;
    expect(order.workspaces["p-alpha"]).toEqual(["w-apple", "w-banana", "wsg-1"]);
    expect(order.groupMembers?.["wsg-1"]).toEqual(["w-elder", "w-cherry"]);
  });
});
