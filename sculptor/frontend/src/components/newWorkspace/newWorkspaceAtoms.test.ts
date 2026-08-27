import { createStore } from "jotai";
import { describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { Workspace } from "~/api";
import { updateWorkspacesAtom, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";

import { shouldOfferFirstRunWorkspaceAtom } from "./newWorkspaceAtoms.ts";

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return {
    ...actual,
    updateWorkspace: vi.fn().mockResolvedValue({ data: {} }),
    batchUpdateOpenState: vi.fn().mockResolvedValue({ data: {} }),
  };
});

const mockWorkspace = (overrides: Partial<Workspace> & Pick<Workspace, "objectId">): Workspace =>
  ({
    projectId: "p1",
    organizationReference: "org-1",
    description: `ws-${overrides.objectId}`,
    initializationStrategy: "CLONE",
    isOpen: true,
    isDeleted: false,
    ...overrides,
  }) as Workspace;

describe("shouldOfferFirstRunWorkspaceAtom", () => {
  it("stays false while the workspace list is still loading", () => {
    // Before the first snapshot arrives the list is undefined. The first-run
    // dialog must not flash on a boot that turns out to have workspaces.
    const store = createStore();
    expect(store.get(workspaceIdsAtom)).toBeUndefined();
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(false);
  });

  it("flips true once the first snapshot loads an empty list", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, []);
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(true);
  });

  it("is false while a workspace exists", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1" })]);
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(false);
  });

  it("stays false after the last workspace is deleted mid-session", () => {
    // The offer is an onboarding affordance for a boot with zero workspaces.
    // A session that had a workspace and then deleted it lands on a plain
    // empty Home — re-opening the dialog there would fight the user's intent.
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1" })]);
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1", isDeleted: true })]);
    expect(store.get(workspaceIdsAtom)).toEqual([]);
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(false);
  });

  it("offers on a boot whose first snapshot is empty even after later creates and deletes", () => {
    // Boot-empty offer, first workspace created, then deleted: the gate must
    // not reopen — the latch records "had a workspace", not "was ever empty".
    const store = createStore();
    store.set(updateWorkspacesAtom, []);
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(true);
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1" })]);
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(false);
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1", isDeleted: true })]);
    expect(store.get(shouldOfferFirstRunWorkspaceAtom)).toBe(false);
  });
});
