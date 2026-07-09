import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { Project, Workspace } from "~/api";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects.ts";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";
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

// A workspace carrying the creation fields the default order keys on: createdAt
// (newest-first) and createdBy.createdByWorkspaceId (the creator it nests beneath).
const makeAttributedWorkspace = (
  id: string,
  projectId: string,
  description: string,
  options: { createdAt?: string; createdByWorkspaceId?: string },
): Workspace =>
  ({
    objectId: id,
    projectId,
    description,
    createdAt: options.createdAt,
    createdBy:
      options.createdByWorkspaceId !== undefined ? { createdByWorkspaceId: options.createdByWorkspaceId } : undefined,
  }) as unknown as Workspace;

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
  it("defaults to alphabetical groups; workspaces without createdAt tie-break by description", () => {
    const groups = groupWorkspacesByRepo(WORKSPACES, PROJECTS);
    expect(groups.map((group) => group.projectId)).toEqual(["p-alpha", "p-beta"]);
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-apple", "w-banana", "w-cherry"]);
  });

  it("renders stored workspace positions first, then unstored ones in default order", () => {
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

describe("groupWorkspacesByRepo creation ordering and nesting", () => {
  it("orders top-level workspaces newest-first by createdAt", () => {
    const workspaces = [
      makeAttributedWorkspace("w-old", "p-alpha", "old", { createdAt: "2026-01-01T00:00:00Z" }),
      makeAttributedWorkspace("w-new", "p-alpha", "new", { createdAt: "2026-03-01T00:00:00Z" }),
      makeAttributedWorkspace("w-mid", "p-alpha", "mid", { createdAt: "2026-02-01T00:00:00Z" }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-new", "w-mid", "w-old"]);
  });

  it("nests an agent-spawned workspace directly beneath its creator", () => {
    const workspaces = [
      makeAttributedWorkspace("w-parent", "p-alpha", "parent", { createdAt: "2026-01-01T00:00:00Z" }),
      makeAttributedWorkspace("w-top", "p-alpha", "top", { createdAt: "2026-03-01T00:00:00Z" }),
      makeAttributedWorkspace("w-child", "p-alpha", "child", {
        createdAt: "2026-02-01T00:00:00Z",
        createdByWorkspaceId: "w-parent",
      }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    // w-top is newest so it leads; w-parent follows with its child directly beneath,
    // even though the child was created more recently than the parent.
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-top", "w-parent", "w-child"]);
  });

  it("orders sibling children newest-first under their creator", () => {
    const workspaces = [
      makeAttributedWorkspace("w-parent", "p-alpha", "parent", { createdAt: "2026-01-01T00:00:00Z" }),
      makeAttributedWorkspace("w-child-old", "p-alpha", "child-old", {
        createdAt: "2026-01-02T00:00:00Z",
        createdByWorkspaceId: "w-parent",
      }),
      makeAttributedWorkspace("w-child-new", "p-alpha", "child-new", {
        createdAt: "2026-01-03T00:00:00Z",
        createdByWorkspaceId: "w-parent",
      }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-parent", "w-child-new", "w-child-old"]);
  });

  it("nests grandchildren recursively down the creation chain", () => {
    const workspaces = [
      makeAttributedWorkspace("w-a", "p-alpha", "a", { createdAt: "2026-01-01T00:00:00Z" }),
      makeAttributedWorkspace("w-b", "p-alpha", "b", {
        createdAt: "2026-01-02T00:00:00Z",
        createdByWorkspaceId: "w-a",
      }),
      makeAttributedWorkspace("w-c", "p-alpha", "c", {
        createdAt: "2026-01-03T00:00:00Z",
        createdByWorkspaceId: "w-b",
      }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-a", "w-b", "w-c"]);
  });

  it("treats a workspace whose creator lives in another repo as top-level", () => {
    const workspaces = [
      makeAttributedWorkspace("w-parent", "p-beta", "parent", { createdAt: "2026-01-01T00:00:00Z" }),
      makeAttributedWorkspace("w-orphan", "p-alpha", "orphan", {
        createdAt: "2026-01-02T00:00:00Z",
        createdByWorkspaceId: "w-parent",
      }),
      makeAttributedWorkspace("w-plain", "p-alpha", "plain", { createdAt: "2026-01-03T00:00:00Z" }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    // w-parent isn't in p-alpha, so w-orphan roots at the top level and sorts by its
    // own createdAt rather than nesting.
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-plain", "w-orphan"]);
  });

  it("treats a self-referential creator as top-level", () => {
    const workspaces = [
      makeAttributedWorkspace("w-self", "p-alpha", "self", {
        createdAt: "2026-01-01T00:00:00Z",
        createdByWorkspaceId: "w-self",
      }),
      makeAttributedWorkspace("w-other", "p-alpha", "other", { createdAt: "2026-01-02T00:00:00Z" }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    expect(workspaceIdsOf(groups, "p-alpha")).toEqual(["w-other", "w-self"]);
  });

  it("still renders every workspace when creators form a cycle", () => {
    const workspaces = [
      makeAttributedWorkspace("w-x", "p-alpha", "x", {
        createdAt: "2026-01-01T00:00:00Z",
        createdByWorkspaceId: "w-y",
      }),
      makeAttributedWorkspace("w-y", "p-alpha", "y", {
        createdAt: "2026-01-02T00:00:00Z",
        createdByWorkspaceId: "w-x",
      }),
    ];
    const groups = groupWorkspacesByRepo(workspaces, PROJECTS);
    expect([...workspaceIdsOf(groups, "p-alpha")].sort()).toEqual(["w-x", "w-y"]);
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
