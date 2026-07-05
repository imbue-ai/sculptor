import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import type { WorkspaceLayoutState } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import {
  closePanelAtom,
  closeSplitAtom,
  consumePendingPanelRevealAtom,
  jumpToSectionAtom,
  movePanelAtom,
  openPanelAtom,
  revealPanelInWorkspaceAtom,
  setActiveSectionAtom,
  setSplitRatioAtom,
  SPLIT_RATIO_MAX,
  SPLIT_RATIO_MIN,
  splitSectionAtom,
  toggleSectionAtom,
} from "./sectionActions.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom, workspaceLayoutFamily } from "./sectionAtoms.ts";
import { activeSectionRingNonceAtom, maximizedSectionAtom } from "./transientAtoms.ts";

const storeWith = (layout: Partial<WorkspaceLayoutState>, workspaceId = "ws-test"): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, workspaceId);
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
  return store;
};

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

  it("collapsing the maximized section clears the maximize", () => {
    const store = storeWith({ expanded: { left: true } });
    store.set(maximizedSectionAtom, "left");
    store.set(toggleSectionAtom, { section: "left" });
    expect(store.get(workspaceLayoutAtom).expanded.left).toBe(false);
    expect(store.get(maximizedSectionAtom)).toBeNull();
  });

  it("collapsing a different section keeps the maximize", () => {
    const store = storeWith({ expanded: { left: true } });
    store.set(maximizedSectionAtom, "center");
    store.set(toggleSectionAtom, { section: "left" });
    expect(store.get(maximizedSectionAtom)).toBe("center");
  });

  it("expanding a section leaves the maximize untouched", () => {
    const store = storeWith({ expanded: { left: false } });
    store.set(maximizedSectionAtom, "left");
    store.set(toggleSectionAtom, { section: "left" });
    expect(store.get(workspaceLayoutAtom).expanded.left).toBe(true);
    expect(store.get(maximizedSectionAtom)).toBe("left");
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

  it("relocates an already-open multi-instance panel instead of leaving it stale in the source", () => {
    const store = storeWith({
      placement: { "agent:1": "center", "agent:2": "center" },
      order: { center: ["agent:1", "agent:2"] },
      activePanel: { center: "agent:2" },
    });
    store.set(openPanelAtom, { panelId: "agent:2", in: "right" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement["agent:2"]).toBe("right");
    // No stale id or active-panel entry is left behind in the source sub-section.
    expect(layout.order.center).toEqual(["agent:1"]);
    expect(layout.order.right).toEqual(["agent:2"]);
    expect(layout.activePanel.center).toBe("agent:1");
    expect(layout.activePanel.right).toBe("agent:2");
    expect(layout.expanded.right).toBe(true);
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

  it("closing the last panel in a split half keeps the split with an empty half", () => {
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
    expect(layout.splits.center).toBeDefined();
    expect(layout.placement["agent:2"]).toBeUndefined();
    expect(layout.order["center:secondary"] ?? []).toEqual([]);
    expect(layout.activePanel["center:secondary"]).toBeUndefined();
    // The other half is untouched, and the emptied half stays the active sub-section
    // (it still renders, as the empty-section state).
    expect(layout.placement["agent:1"]).toBe("center");
    expect(layout.activePanel.center).toBe("agent:1");
    expect(layout.activeSubSection).toBe("center:secondary");
  });

  it("moving the only panel out of a split half keeps the split with an empty half", () => {
    const store = storeWith({
      placement: { "agent:1": "center", "agent:2": "center:secondary" },
      order: { center: ["agent:1"], "center:secondary": ["agent:2"] },
      splits: { center: { axis: "vertical", ratio: 0.5 } },
      activePanel: { center: "agent:1", "center:secondary": "agent:2" },
    });
    store.set(movePanelAtom, { panelId: "agent:2", to: "center" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.splits.center).toBeDefined();
    expect(layout.placement["agent:2"]).toBe("center");
    expect(layout.order.center).toEqual(["agent:1", "agent:2"]);
    expect(layout.order["center:secondary"]).toEqual([]);
    expect(layout.activePanel["center:secondary"]).toBeUndefined();
  });

  it("closeSplit on a split with an empty secondary drops the split and keeps the primary sane", () => {
    const store = storeWith({
      placement: { "agent:1": "center" },
      order: { center: ["agent:1"], "center:secondary": [] },
      splits: { center: { axis: "vertical", ratio: 0.5 } },
      activePanel: { center: "agent:1" },
      activeSubSection: "center:secondary",
    });
    store.set(closeSplitAtom, { section: "center" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.splits.center).toBeUndefined();
    expect(layout.order.center).toEqual(["agent:1"]);
    expect(layout.activePanel.center).toBe("agent:1");
    expect(layout.activePanel["center:secondary"]).toBeUndefined();
    expect(layout.activeSubSection).toBe("center");
  });

  it("an empty split half can still become the active sub-section", () => {
    const store = storeWith({
      placement: { "agent:1": "center" },
      order: { center: ["agent:1"], "center:secondary": [] },
      splits: { center: { axis: "vertical", ratio: 0.5 } },
      activeSubSection: "center",
    });
    store.set(setActiveSectionAtom, { subSection: "center:secondary" });
    expect(store.get(workspaceLayoutAtom).activeSubSection).toBe("center:secondary");
  });

  it("opening a panel into an empty split half lands it in that half", () => {
    const store = storeWith({
      placement: { "agent:1": "center" },
      order: { center: ["agent:1"], "center:secondary": [] },
      splits: { center: { axis: "vertical", ratio: 0.5 } },
    });
    store.set(openPanelAtom, { panelId: "notes", in: "center:secondary" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.splits.center).toBeDefined();
    expect(layout.placement.notes).toBe("center:secondary");
    expect(layout.order["center:secondary"]).toEqual(["notes"]);
    expect(layout.activePanel["center:secondary"]).toBe("notes");
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

  it("reorders a panel within its sub-section without reassigning the active panel", () => {
    const store = storeWith({
      placement: { files: "left", changes: "left", commits: "left" },
      order: { left: ["files", "changes", "commits"] },
      activePanel: { left: "changes" },
      expanded: { left: true },
    });
    // The index is interpreted against the array with the dragged panel removed
    // ([changes, commits]), matching PanelDndProvider.computeDropIndex.
    store.set(movePanelAtom, { panelId: "files", to: "left", index: 2 });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.order.left).toEqual(["changes", "commits", "files"]);
    // A same-sub-section reorder must not steal the active panel.
    expect(layout.activePanel.left).toBe("changes");
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

  it("ignores jumping into a collapsed section: no active change, no ring pulse", () => {
    const store = storeWith({ activeSubSection: "center", expanded: { left: false } });
    const nonceBefore = store.get(activeSectionRingNonceAtom);

    store.set(jumpToSectionAtom, { subSection: "left" });
    expect(store.get(workspaceLayoutAtom).activeSubSection).toBe("center");
    expect(store.get(activeSectionRingNonceAtom)).toBe(nonceBefore);
  });

  it("ignores jumping into a collapsed section's split half", () => {
    // The split persists while its section is collapsed; jumping to the hidden
    // secondary must not activate an invisible pane (or pulse the ring).
    const store = storeWith({
      activeSubSection: "center",
      expanded: { left: false },
      splits: { left: { axis: "horizontal", ratio: 0.5 } },
    });
    const nonceBefore = store.get(activeSectionRingNonceAtom);

    store.set(jumpToSectionAtom, { subSection: "left:secondary" });
    expect(store.get(workspaceLayoutAtom).activeSubSection).toBe("center");
    expect(store.get(activeSectionRingNonceAtom)).toBe(nonceBefore);
  });
});

describe("cross-workspace panel reveal", () => {
  it("applies immediately when the target workspace is the active scope", () => {
    const store = storeWith({}, "ws-reveal-active");
    store.set(revealPanelInWorkspaceAtom, { workspaceId: "ws-reveal-active", panelId: "changes", in: "left" });
    const layout = store.get(workspaceLayoutAtom);
    expect(layout.placement.changes).toBe("left");
    expect(layout.expanded.left).toBe(true);
    expect(layout.activeSubSection).toBe("left");
  });

  it("defers a reveal for a non-active workspace, leaving the departed layout untouched", () => {
    const store = storeWith({}, "ws-reveal-from");
    store.set(revealPanelInWorkspaceAtom, { workspaceId: "ws-reveal-to", panelId: "changes", in: "left" });
    // The workspace being left gains nothing.
    const departedLayout = store.get(workspaceLayoutFamily("ws-reveal-from"));
    expect(departedLayout.placement.changes).toBeUndefined();
    expect(departedLayout.expanded.left).toBeUndefined();

    // Once the scope flips to the destination (as the shell bootstrap does),
    // consuming the pending reveal opens the panel there.
    store.set(activeWorkspaceIdAtom, "ws-reveal-to");
    store.set(consumePendingPanelRevealAtom, { workspaceId: "ws-reveal-to" });
    const layout = store.get(workspaceLayoutFamily("ws-reveal-to"));
    expect(layout.placement.changes).toBe("left");
    expect(layout.expanded.left).toBe(true);
    expect(layout.activeSubSection).toBe("left");
  });

  it("drops a stale reveal whose target workspace was never entered", () => {
    const store = storeWith({}, "ws-reveal-from");
    store.set(revealPanelInWorkspaceAtom, { workspaceId: "ws-reveal-missed", panelId: "changes", in: "left" });

    // Entering a DIFFERENT workspace clears the pending reveal without applying it.
    store.set(activeWorkspaceIdAtom, "ws-reveal-other");
    store.set(consumePendingPanelRevealAtom, { workspaceId: "ws-reveal-other" });
    expect(store.get(workspaceLayoutFamily("ws-reveal-other")).placement.changes).toBeUndefined();

    // A later visit to the original target no longer fires the dropped reveal.
    store.set(activeWorkspaceIdAtom, "ws-reveal-missed");
    store.set(consumePendingPanelRevealAtom, { workspaceId: "ws-reveal-missed" });
    expect(store.get(workspaceLayoutFamily("ws-reveal-missed")).placement.changes).toBeUndefined();
  });
});
