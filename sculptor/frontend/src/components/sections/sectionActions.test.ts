import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { WorkspaceLayoutState } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import {
  closePanelAtom,
  closeSplitAtom,
  jumpToSectionAtom,
  movePanelAtom,
  openPanelAtom,
  setActiveSectionAtom,
  setSplitRatioAtom,
  SPLIT_RATIO_MAX,
  SPLIT_RATIO_MIN,
  splitSectionAtom,
  toggleSectionAtom,
} from "./sectionActions.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { activeSectionRingNonceAtom } from "./transientAtoms.ts";

function storeWith(layout: Partial<WorkspaceLayoutState>, workspaceId = "ws-test"): ReturnType<typeof createStore> {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, workspaceId);
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
  return store;
}

beforeEach(() => {
  localStorage.clear();
});

describe("collapse/expand invariants", () => {
  it("toggleSection is a no-op for center", () => {
    const store = storeWith({ activeSubSection: "center" });
    store.set(toggleSectionAtom, { section: "center" });
    expect(store.get(workspaceLayoutAtom).expanded.center).toBeUndefined();
    expect(store.get(workspaceLayoutAtom).activeSubSection).toBe("center");
  });

  it("collapsing the section holding the active sub-section reassigns active to center", () => {
    const store = storeWith({ expanded: { left: true }, activeSubSection: "left" });
    store.set(toggleSectionAtom, { section: "left" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.expanded.left).toBe(false);
    expect(layout.activeSubSection).toBe("center");
  });
});

describe("single-instance invariant", () => {
  it("opening an already-open single-instance panel activates it in place (no duplicate)", () => {
    const store = storeWith({
      placement: { files: "left" },
      order: { left: ["files"] },
      activePanel: { left: "files" },
      expanded: { left: true },
    });
    store.set(openPanelAtom, { panelId: "files", in: "right" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement.files).toBe("left");
    expect(layout.order.left).toEqual(["files"]);
    expect(layout.order.right ?? []).toEqual([]);
  });

  it("opening multiple agent panels does not dedupe", () => {
    const store = storeWith({});
    store.set(openPanelAtom, { panelId: "agent:1", in: "center" });
    store.set(openPanelAtom, { panelId: "agent:2", in: "center" });
    expect(store.get(workspaceLayoutAtom).order.center).toEqual(["agent:1", "agent:2"]);
  });
});

describe("split invariants", () => {
  it("rejects a second split (one split per section)", () => {
    const store = storeWith({
      placement: { "agent:1": "center", "agent:2": "center" },
      order: { center: ["agent:1", "agent:2"] },
    });
    store.set(splitSectionAtom, { section: "center", panelId: "agent:2", axis: "horizontal" });
    store.set(splitSectionAtom, { section: "center", panelId: "agent:1", axis: "vertical" });
    expect(store.get(workspaceLayoutAtom).splits.center?.axis).toBe("horizontal");
  });

  it("rejects a split with a disallowed axis for the section", () => {
    const store = storeWith({ placement: { files: "left" }, order: { left: ["files"] }, expanded: { left: true } });
    store.set(splitSectionAtom, { section: "left", panelId: "files", axis: "vertical" });
    expect(store.get(workspaceLayoutAtom).splits.left).toBeUndefined();
  });

  it("self-heals: emptying a split secondary closes the split and merges back", () => {
    const store = storeWith({
      placement: { "agent:1": "center", "agent:2": "center" },
      order: { center: ["agent:1", "agent:2"] },
      activePanel: { center: "agent:1" },
    });
    store.set(splitSectionAtom, { section: "center", panelId: "agent:2", axis: "vertical" });
    expect(store.get(workspaceLayoutAtom).splits.center).toBeDefined();
    expect(store.get(workspaceLayoutAtom).placement["agent:2"]).toBe("center:secondary");

    store.set(closePanelAtom, { panelId: "agent:2" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.splits.center).toBeUndefined();
    expect(layout.placement["agent:1"]).toBe("center");
  });

  it("does not self-heal a split whose half holds a not-yet-loaded dynamic panel", () => {
    const store = storeWith({
      placement: { files: "left", "agent:1": "left:secondary" },
      order: { left: ["files"] }, // agent:1 placed but not yet ordered (mid-load)
      splits: { left: { axis: "horizontal", ratio: 0.5 } },
      expanded: { left: true },
    });
    store.set(setActiveSectionAtom, { subSection: "left" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.splits.left).toBeDefined();
    expect(layout.placement["agent:1"]).toBe("left:secondary");
  });

  it("closeSplit merges the secondary back into the primary preserving order", () => {
    const store = storeWith({
      placement: { "agent:1": "center", "agent:2": "center:secondary" },
      order: { center: ["agent:1"], "center:secondary": ["agent:2"] },
      splits: { center: { axis: "vertical", ratio: 0.5 } },
      activeSubSection: "center:secondary",
    });
    store.set(closeSplitAtom, { section: "center" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.splits.center).toBeUndefined();
    expect(layout.order.center).toEqual(["agent:1", "agent:2"]);
    expect(layout.placement["agent:2"]).toBe("center");
    expect(layout.activeSubSection).toBe("center");
  });

  it("clamps the split ratio to its bounds", () => {
    const store = storeWith({ splits: { center: { axis: "vertical", ratio: 0.5 } } });
    store.set(setSplitRatioAtom, { section: "center", ratio: 0.95 });
    expect(store.get(workspaceLayoutAtom).splits.center?.ratio).toBe(SPLIT_RATIO_MAX);
    store.set(setSplitRatioAtom, { section: "center", ratio: 0.01 });
    expect(store.get(workspaceLayoutAtom).splits.center?.ratio).toBe(SPLIT_RATIO_MIN);
  });
});

describe("move + close", () => {
  it("moving a panel to another section makes it active there and expands that section", () => {
    const store = storeWith({
      placement: { files: "left" },
      order: { left: ["files"] },
      activePanel: { left: "files" },
      expanded: { left: true },
    });
    store.set(movePanelAtom, { panelId: "files", to: "right" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement.files).toBe("right");
    expect(layout.activePanel.right).toBe("files");
    expect(layout.expanded.right).toBe(true);
  });

  it("closing the active panel selects another open panel in the same sub-section", () => {
    const store = storeWith({
      placement: { files: "left", changes: "left" },
      order: { left: ["files", "changes"] },
      activePanel: { left: "files" },
      expanded: { left: true },
    });
    store.set(closePanelAtom, { panelId: "files" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement.files).toBeUndefined();
    expect(layout.activePanel.left).toBe("changes");
  });

  it("closing the last panel leaves the section expanded but empty", () => {
    const store = storeWith({
      placement: { "agent:1": "center" },
      order: { center: ["agent:1"] },
      activePanel: { center: "agent:1" },
    });
    store.set(closePanelAtom, { panelId: "agent:1" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement["agent:1"]).toBeUndefined();
    expect(layout.order.center ?? []).toEqual([]);
  });
});

describe("active section: silent vs. pulsing", () => {
  it("setActiveSection does not bump the ring nonce; jumpToSection does", () => {
    const store = storeWith({ activeSubSection: "center" });
    const nonceBefore = store.get(activeSectionRingNonceAtom);

    store.set(setActiveSectionAtom, { subSection: "center" });
    expect(store.get(activeSectionRingNonceAtom)).toBe(nonceBefore);

    store.set(jumpToSectionAtom, { subSection: "center" });
    expect(store.get(activeSectionRingNonceAtom)).toBe(nonceBefore + 1);
  });

  it("ignores activating a collapsed (non-center) section", () => {
    const store = storeWith({ activeSubSection: "center", expanded: { left: false } });
    store.set(setActiveSectionAtom, { subSection: "left" });
    expect(store.get(workspaceLayoutAtom).activeSubSection).toBe("center");
  });
});
