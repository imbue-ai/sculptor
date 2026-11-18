import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { WorkspaceJjStateInfo } from "~/api";
import { updateWorkspaceJjStatesAtom, workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState";

const makeJjState = (workspaceId: string, overrides: Partial<WorkspaceJjStateInfo> = {}): WorkspaceJjStateInfo => ({
  workspaceId,
  workingCopyChangeId: "kxqpmzvykxqpmzvykxqpmzvykxqpmzvy",
  workingCopyChangeIdPrefixLength: 2,
  workingCopyDescription: "",
  isWorkingCopyEmpty: true,
  bookmarks: [],
  primaryBookmark: null,
  unbookmarkedRevisionCount: 0,
  hasConflict: false,
  isDivergent: false,
  isWorkingCopyStale: false,
  ...overrides,
});

describe("updateWorkspaceJjStatesAtom", () => {
  it("has no state for a workspace the stream has not described", () => {
    const store = createStore();

    expect(store.get(workspaceJjStateAtomFamily("ws-a"))).toBeNull();
  });

  it("stores each workspace's state from a frame", () => {
    const store = createStore();
    const stateA = makeJjState("ws-a", { primaryBookmark: "feature", bookmarks: ["feature"] });
    const stateB = makeJjState("ws-b");

    store.set(updateWorkspaceJjStatesAtom, { "ws-a": stateA, "ws-b": stateB });

    expect(store.get(workspaceJjStateAtomFamily("ws-a"))).toEqual(stateA);
    expect(store.get(workspaceJjStateAtomFamily("ws-b"))).toEqual(stateB);
  });

  it("keeps the state of a workspace a later frame does not mention", () => {
    const store = createStore();
    const stateA = makeJjState("ws-a");
    store.set(updateWorkspaceJjStatesAtom, { "ws-a": stateA });

    store.set(updateWorkspaceJjStatesAtom, { "ws-b": makeJjState("ws-b") });

    expect(store.get(workspaceJjStateAtomFamily("ws-a"))).toEqual(stateA);
  });
});
