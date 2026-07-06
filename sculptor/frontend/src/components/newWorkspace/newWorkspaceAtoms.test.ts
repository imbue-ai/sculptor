import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";

import { areGlobalShortcutsDisabledAtom, isWorkspaceListEmptyAtom } from "./newWorkspaceAtoms.ts";

const seedWorkspace = (store: ReturnType<typeof createStore>, id: string): void => {
  store.set(workspaceAtomFamily(id), {
    objectId: id,
    description: `ws-${id}`,
    projectId: "p1",
  } as unknown as Workspace);
  store.set(workspaceIdsAtom, [id]);
};

describe("areGlobalShortcutsDisabledAtom", () => {
  it("disables shortcuts while the workspace list is still loading", () => {
    // Before the first snapshot arrives the list is undefined. Shortcuts must
    // already be off: a Cmd/Meta+T fired in this window on a zero-workspace
    // boot would set the new-workspace modal open right before the first-run
    // swap unmounts its host, leaving a stale request that pops the dialog
    // over the first workspace created from the inline form.
    const store = createStore();
    expect(store.get(workspaceIdsAtom)).toBeUndefined();
    expect(store.get(areGlobalShortcutsDisabledAtom)).toBe(true);
  });

  it("keeps the empty first-run page from flashing while the list is loading", () => {
    // The two atoms deliberately diverge during load: the page gate stays
    // false (no empty-page flash) while the shortcut gate is already on.
    const store = createStore();
    expect(store.get(isWorkspaceListEmptyAtom)).toBe(false);
    expect(store.get(areGlobalShortcutsDisabledAtom)).toBe(true);
  });

  it("disables shortcuts when the loaded list is empty", () => {
    const store = createStore();
    store.set(workspaceIdsAtom, []);
    expect(store.get(isWorkspaceListEmptyAtom)).toBe(true);
    expect(store.get(areGlobalShortcutsDisabledAtom)).toBe(true);
  });

  it("enables shortcuts once a workspace exists", () => {
    const store = createStore();
    seedWorkspace(store, "w1");
    expect(store.get(isWorkspaceListEmptyAtom)).toBe(false);
    expect(store.get(areGlobalShortcutsDisabledAtom)).toBe(false);
  });
});
