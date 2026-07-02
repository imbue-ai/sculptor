import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";

import {
  activeDiffTabAtomFamily,
  closeDiffTabAtom,
  diffPanelStateAtomFamily,
  diffScopeAtomFamily,
  openFileViewTabAtom,
  resetReviewAllScopeAtom,
} from "./atoms.ts";

const WORKSPACE_ID = "ws-1";

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe("closeDiffTabAtom", () => {
  it("clears the active tab when closing it (the host panel shows its empty placeholder)", () => {
    const store = createStore();
    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "only.ts" });
    const activeTabPath = store.get(diffPanelStateAtomFamily(WORKSPACE_ID)).activeTab!.filePath;

    store.set(closeDiffTabAtom, { workspaceId: WORKSPACE_ID, filePath: activeTabPath });

    expect(store.get(activeDiffTabAtomFamily(WORKSPACE_ID))).toBeNull();
  });

  it("is a no-op when the given path is not the active tab", () => {
    const store = createStore();
    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "keep.ts" });
    const before = store.get(activeDiffTabAtomFamily(WORKSPACE_ID));
    expect(before).not.toBeNull();

    store.set(closeDiffTabAtom, { workspaceId: WORKSPACE_ID, filePath: "unrelated.ts" });

    expect(store.get(activeDiffTabAtomFamily(WORKSPACE_ID))).toEqual(before);
  });
});

describe("openFileViewTabAtom", () => {
  it("replaces the active tab — only the most recently opened tab is kept", () => {
    const store = createStore();
    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "a.ts" });
    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "b.ts" });

    const activeTab = store.get(activeDiffTabAtomFamily(WORKSPACE_ID));
    expect(activeTab?.kind).toBe("file-view");
    if (activeTab?.kind === "file-view") {
      expect(activeTab.realPath).toBe("b.ts");
    }
  });
});

describe("resetReviewAllScopeAtom", () => {
  it("resets the ACTIVE workspace's combined-diff scope to All (vs the target branch)", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, WORKSPACE_ID);
    store.set(diffScopeAtomFamily(WORKSPACE_ID), "uncommitted");

    store.set(resetReviewAllScopeAtom);

    expect(store.get(diffScopeAtomFamily(WORKSPACE_ID))).toBe("vs-target-branch");
  });

  it("is a no-op when no workspace is active", () => {
    const store = createStore();
    store.set(diffScopeAtomFamily(WORKSPACE_ID), "uncommitted");

    store.set(resetReviewAllScopeAtom);

    expect(store.get(diffScopeAtomFamily(WORKSPACE_ID))).toBe("uncommitted");
  });
});
