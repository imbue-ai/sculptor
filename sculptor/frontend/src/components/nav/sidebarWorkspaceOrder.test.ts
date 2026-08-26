import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { Project, Workspace } from "~/api";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects.ts";
import {
  optimisticDeleteWorkspaceAtom,
  workspaceAtomFamily,
  workspaceIdsAtom,
} from "~/common/state/atoms/workspaces.ts";
import { layoutPersistenceAdapter } from "~/components/sections/persistence/LocalStorageLayoutAdapter.ts";
import { globalLayoutAtom } from "~/components/sections/sectionAtoms.ts";

import {
  groupWorkspacesByRepo,
  reorderSidebarRepoGroupAtom,
  reorderSidebarWorkspaceAtom,
  sidebarOrderedWorkspacesAtom,
  sidebarWorkspaceGroupsAtom,
} from "./sidebarWorkspaceOrder.ts";

const makeWorkspace = (id: string, projectId: string, description: string): Workspace =>
  ({ objectId: id, projectId, description }) as unknown as Workspace;

const makeProject = (id: string, name: string): Project => ({ objectId: id, name }) as unknown as Project;

const PROJECTS = [makeProject("p-alpha", "alpha"), makeProject("p-beta", "beta")];
const WORKSPACES = [
  makeWorkspace("w-apple", "p-alpha", "apple"),
  makeWorkspace("w-banana", "p-alpha", "banana"),
  makeWorkspace("w-cherry", "p-alpha", "cherry"),
  makeWorkspace("w-dates", "p-beta", "dates"),
];

const workspaceIdsOf = (groups: ReturnType<typeof groupWorkspacesByRepo>, projectId: string): Array<string> =>
  groups.find((group) => group.projectId === projectId)?.workspaces.map((ws) => ws.objectId) ?? [];

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
});

describe("sidebar reorder atoms", () => {
  const seedStore = (store: ReturnType<typeof createStore>): void => {
    for (const project of PROJECTS) {
      store.set(projectAtomFamily(project.objectId), project);
    }
    store.set(
      projectIdsAtom,
      PROJECTS.map((project) => project.objectId),
    );
    for (const workspace of WORKSPACES) {
      store.set(workspaceAtomFamily(workspace.objectId), workspace);
    }
    store.set(
      workspaceIdsAtom,
      WORKSPACES.map((workspace) => workspace.objectId),
    );
  };

  it("moves a workspace to the drop slot and stores the group's full order", () => {
    const store = createStore();
    seedStore(store);

    store.set(reorderSidebarWorkspaceAtom, {
      projectId: "p-alpha",
      activeWorkspaceId: "w-cherry",
      overWorkspaceId: "w-apple",
    });

    expect(workspaceIdsOf(store.get(sidebarWorkspaceGroupsAtom), "p-alpha")).toEqual([
      "w-cherry",
      "w-apple",
      "w-banana",
    ]);
    // The full visible order is materialized, so later fallback merging is exact.
    expect(store.get(globalLayoutAtom).sidebarOrder.workspaces["p-alpha"]).toEqual(["w-cherry", "w-apple", "w-banana"]);
  });

  it("keeps keyboard cycling's flattened order in lockstep with the rendered groups", () => {
    const store = createStore();
    seedStore(store);

    store.set(reorderSidebarWorkspaceAtom, {
      projectId: "p-alpha",
      activeWorkspaceId: "w-apple",
      overWorkspaceId: "w-cherry",
    });

    const flattened = store.get(sidebarWorkspaceGroupsAtom).flatMap((group) => group.workspaces);
    expect(store.get(sidebarOrderedWorkspacesAtom)).toEqual(flattened);
    expect(flattened.map((workspace) => workspace.objectId)).toEqual(["w-banana", "w-cherry", "w-apple", "w-dates"]);
  });

  it("keeps a delete-in-flight row in the rendered groups but out of keyboard cycling", () => {
    const store = createStore();
    seedStore(store);

    store.set(optimisticDeleteWorkspaceAtom, "w-banana");

    // The groups still list it (its row renders as "Deleting\u2026")\u2026
    const flattened = store.get(sidebarWorkspaceGroupsAtom).flatMap((group) => group.workspaces);
    expect(flattened.map((workspace) => workspace.objectId)).toContain("w-banana");
    // \u2026but cycling steps over it: a non-navigable row must not be a cycling stop.
    expect(store.get(sidebarOrderedWorkspacesAtom).map((workspace) => workspace.objectId)).toEqual([
      "w-apple",
      "w-cherry",
      "w-dates",
    ]);
  });

  it("moves a repo group to the drop slot and stores the full group order", () => {
    const store = createStore();
    seedStore(store);

    store.set(reorderSidebarRepoGroupAtom, { activeProjectId: "p-beta", overProjectId: "p-alpha" });

    expect(store.get(sidebarWorkspaceGroupsAtom).map((group) => group.projectId)).toEqual(["p-beta", "p-alpha"]);
    expect(store.get(globalLayoutAtom).sidebarOrder.repos).toEqual(["p-beta", "p-alpha"]);
  });

  it("persists the committed order through the layout adapter", () => {
    const store = createStore();
    seedStore(store);

    store.set(reorderSidebarWorkspaceAtom, {
      projectId: "p-alpha",
      activeWorkspaceId: "w-banana",
      overWorkspaceId: "w-apple",
    });

    // globalLayoutAtom writes through the adapter (read-your-writes even inside
    // the debounce window), so the custom order survives the next app start.
    const persisted = layoutPersistenceAdapter.read({ kind: "global" });
    expect(persisted?.sidebarOrder.workspaces["p-alpha"]).toEqual(["w-banana", "w-apple", "w-cherry"]);
  });

  it("ignores drops whose ids don't resolve to the group's rows", () => {
    const store = createStore();
    seedStore(store);
    const before = store.get(globalLayoutAtom);

    store.set(reorderSidebarWorkspaceAtom, {
      projectId: "p-alpha",
      activeWorkspaceId: "w-unknown",
      overWorkspaceId: "w-apple",
    });
    store.set(reorderSidebarRepoGroupAtom, { activeProjectId: "p-unknown", overProjectId: "p-alpha" });

    expect(store.get(globalLayoutAtom)).toBe(before);
  });
});
