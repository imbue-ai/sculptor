import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { activeWorkspaceIdAtom, workspaceLayoutFamily } from "~/pages/workspace/layout/atoms/section.ts";
import type { WorkspaceLayoutState } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/pages/workspace/layout/persistence/snapshot.ts";

import {
  activeDiffTabAtomFamily,
  closeDiffTabAtom,
  diffPanelStateAtomFamily,
  diffScopeAtomFamily,
  getRecentDiffFilesAtom,
  openFileViewTabAtom,
  recordRecentDiffFileAtom,
  resetReviewAllScopeAtom,
  setActiveDiffTabAtom,
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

describe("recordRecentDiffFileAtom", () => {
  const changesList = getRecentDiffFilesAtom(WORKSPACE_ID, "changes");

  it("replaces the front entry when re-recording the same file with a changed status", () => {
    const store = createStore();
    store.set(recordRecentDiffFileAtom, {
      workspaceId: WORKSPACE_ID,
      panel: "changes",
      entry: { path: "a.ts", status: "M" },
    });
    store.set(recordRecentDiffFileAtom, {
      workspaceId: WORKSPACE_ID,
      panel: "changes",
      entry: { path: "a.ts", status: "A" },
    });

    const list = store.get(changesList);
    expect(list).toHaveLength(1);
    expect(list[0]?.status).toBe("A");
  });

  it("moves a file already deeper in the list to the front without duplicating it", () => {
    const store = createStore();
    for (const path of ["a.ts", "b.ts", "c.ts"]) {
      store.set(recordRecentDiffFileAtom, { workspaceId: WORKSPACE_ID, panel: "changes", entry: { path } });
    }
    store.set(recordRecentDiffFileAtom, { workspaceId: WORKSPACE_ID, panel: "changes", entry: { path: "a.ts" } });

    const list = store.get(changesList);
    expect(list.map((entry) => entry.path)).toEqual(["a.ts", "c.ts", "b.ts"]);
  });

  it("caps the list at the 10 most-recently recorded files", () => {
    const store = createStore();
    for (let i = 0; i < 11; i++) {
      store.set(recordRecentDiffFileAtom, {
        workspaceId: WORKSPACE_ID,
        panel: "changes",
        entry: { path: `file-${i}.ts` },
      });
    }

    const list = store.get(changesList);
    expect(list).toHaveLength(10);
    expect(list[0]?.path).toBe("file-10.ts");
    expect(list.some((entry) => entry.path === "file-0.ts")).toBe(false);
  });
});

describe("setActiveDiffTabAtom", () => {
  const OTHER_WORKSPACE_ID = "ws-2";
  // Any non-empty layout: `isEmptyLayout` is false as soon as a sub-section is
  // active, which is the "bootstrap has seeded the arrangement" signal the reveal
  // guards on.
  const seededLayout: WorkspaceLayoutState = { ...EMPTY_WORKSPACE_LAYOUT, activeSubSection: "center" };

  it("reveals the host panel when the tab's workspace is active and its layout is seeded", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, WORKSPACE_ID);
    store.set(workspaceLayoutFamily(WORKSPACE_ID), seededLayout);

    store.set(setActiveDiffTabAtom, { kind: "single", workspaceId: WORKSPACE_ID, filePath: "a.ts", status: "M" });

    expect(store.get(activeDiffTabAtomFamily(WORKSPACE_ID))?.kind).toBe("single");
    const layout = store.get(workspaceLayoutFamily(WORKSPACE_ID));
    expect(layout.placement.changes).toBe("left");
    expect(layout.activeSubSection).toBe("left");
  });

  it("records the tab but skips the reveal while the layout is still empty (bootstrap race)", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, WORKSPACE_ID);
    store.set(workspaceLayoutFamily(WORKSPACE_ID), EMPTY_WORKSPACE_LAYOUT);

    store.set(setActiveDiffTabAtom, { kind: "single", workspaceId: WORKSPACE_ID, filePath: "a.ts", status: "M" });

    expect(store.get(activeDiffTabAtomFamily(WORKSPACE_ID))?.kind).toBe("single");
    const layout = store.get(workspaceLayoutFamily(WORKSPACE_ID));
    expect(layout.placement.changes).toBeUndefined();
    expect(layout.activeSubSection).toBeNull();
  });

  it("records the tab but leaves the viewed workspace untouched when the tab targets a non-active one", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, OTHER_WORKSPACE_ID);
    store.set(workspaceLayoutFamily(OTHER_WORKSPACE_ID), seededLayout);

    store.set(setActiveDiffTabAtom, { kind: "single", workspaceId: WORKSPACE_ID, filePath: "a.ts", status: "M" });

    expect(store.get(activeDiffTabAtomFamily(WORKSPACE_ID))?.kind).toBe("single");
    // The workspace the user is currently viewing must not gain the Changes panel.
    const viewedLayout = store.get(workspaceLayoutFamily(OTHER_WORKSPACE_ID));
    expect(viewedLayout.placement.changes).toBeUndefined();
    expect(viewedLayout.activeSubSection).toBe("center");
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
