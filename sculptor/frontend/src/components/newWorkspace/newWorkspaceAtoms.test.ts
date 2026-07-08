import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";

import { isWorkspaceListEmptyAtom } from "./newWorkspaceAtoms.ts";

const seedWorkspace = (store: ReturnType<typeof createStore>, id: string): void => {
  store.set(workspaceAtomFamily(id), {
    objectId: id,
    description: `ws-${id}`,
    projectId: "p1",
  } as unknown as Workspace);
  store.set(workspaceIdsAtom, [id]);
};

describe("isWorkspaceListEmptyAtom", () => {
  it("stays false while the workspace list is still loading", () => {
    // Before the first snapshot arrives the list is undefined. The first-run
    // dialog must not flash on a boot that turns out to have workspaces.
    const store = createStore();
    expect(store.get(workspaceIdsAtom)).toBeUndefined();
    expect(store.get(isWorkspaceListEmptyAtom)).toBe(false);
  });

  it("flips true once the loaded list is empty", () => {
    const store = createStore();
    store.set(workspaceIdsAtom, []);
    expect(store.get(isWorkspaceListEmptyAtom)).toBe(true);
  });

  it("is false once a workspace exists", () => {
    const store = createStore();
    seedWorkspace(store, "w1");
    expect(store.get(isWorkspaceListEmptyAtom)).toBe(false);
  });
});
