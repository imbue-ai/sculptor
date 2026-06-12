import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { expandedPanelIdAtom } from "~/components/panels/atoms.ts";

import {
  closeAllDiffTabsAtom,
  closeDiffPanelAtom,
  closeDiffTabAtom,
  diffPanelOpenAtom,
  diffPanelStateAtomFamily,
  openFileViewTabAtom,
} from "./atoms.ts";

const WORKSPACE_ID = "ws-1";

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

// Opens two file-view tabs so each test starts from "panel open, 2 tabs" state.
const seedTwoTabs = (store: ReturnType<typeof createStore>): void => {
  store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "a.ts" });
  store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "b.ts" });
};

describe("closeDiffTabAtom", () => {
  it("when closing the last remaining tab, keeps the panel open and clears the active tab", () => {
    const store = createStore();
    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "only.ts" });

    const onlyTabPath = store.get(diffPanelStateAtomFamily(WORKSPACE_ID)).activeTabPath!;
    expect(store.get(diffPanelOpenAtom)).toBe(true);

    store.set(closeDiffTabAtom, { workspaceId: WORKSPACE_ID, filePath: onlyTabPath, tabCloseBehavior: "mru" });

    const state = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
    expect(state.openTabs).toEqual([]);
    expect(state.activeTabPath).toBeNull();
    // The panel must NOT auto-close — the placeholder is shown instead.
    expect(store.get(diffPanelOpenAtom)).toBe(true);
  });

  it("when closing the last remaining tab, exits expand mode", () => {
    const store = createStore();
    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "only.ts" });
    store.set(expandedPanelIdAtom, "files");

    const onlyTabPath = store.get(diffPanelStateAtomFamily(WORKSPACE_ID)).activeTabPath!;
    store.set(closeDiffTabAtom, { workspaceId: WORKSPACE_ID, filePath: onlyTabPath, tabCloseBehavior: "mru" });

    expect(store.get(expandedPanelIdAtom)).toBeNull();
  });

  it("when closing a non-last tab, keeps the panel open and advances the active tab", () => {
    const store = createStore();
    seedTwoTabs(store);
    const before = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
    expect(before.openTabs).toHaveLength(2);
    const activePath = before.activeTabPath!;

    store.set(closeDiffTabAtom, { workspaceId: WORKSPACE_ID, filePath: activePath, tabCloseBehavior: "mru" });

    const after = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
    expect(after.openTabs).toHaveLength(1);
    expect(after.activeTabPath).not.toBe(activePath);
    expect(store.get(diffPanelOpenAtom)).toBe(true);
  });
});

describe("closeAllDiffTabsAtom", () => {
  it("clears all tabs but leaves the panel open and exits expand mode", () => {
    const store = createStore();
    seedTwoTabs(store);
    store.set(expandedPanelIdAtom, "files");

    store.set(closeAllDiffTabsAtom, { workspaceId: WORKSPACE_ID });

    const state = store.get(diffPanelStateAtomFamily(WORKSPACE_ID));
    expect(state.openTabs).toEqual([]);
    expect(state.activeTabPath).toBeNull();
    expect(store.get(diffPanelOpenAtom)).toBe(true);
    expect(store.get(expandedPanelIdAtom)).toBeNull();
  });
});

describe("closeDiffPanelAtom", () => {
  it("closes the panel and exits expand mode but preserves tabs", () => {
    const store = createStore();
    seedTwoTabs(store);
    store.set(expandedPanelIdAtom, "files");
    const tabsBefore = store.get(diffPanelStateAtomFamily(WORKSPACE_ID)).openTabs;

    store.set(closeDiffPanelAtom);

    expect(store.get(diffPanelOpenAtom)).toBe(false);
    expect(store.get(expandedPanelIdAtom)).toBeNull();
    // Tabs survive panel close — reopening should restore them.
    const tabsAfter = store.get(diffPanelStateAtomFamily(WORKSPACE_ID)).openTabs;
    expect(tabsAfter).toEqual(tabsBefore);
  });
});

describe("openFileViewTabAtom", () => {
  it("opens the panel globally when a file is opened from a closed state", () => {
    const store = createStore();
    expect(store.get(diffPanelOpenAtom)).toBe(false);

    store.set(openFileViewTabAtom, { workspaceId: WORKSPACE_ID, filePath: "a.ts" });

    expect(store.get(diffPanelOpenAtom)).toBe(true);
    expect(store.get(diffPanelStateAtomFamily(WORKSPACE_ID)).openTabs).toHaveLength(1);
  });
});
