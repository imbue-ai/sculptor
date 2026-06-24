import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import { sidebarCollapsedAtom, sidebarWidthAtom } from "../layout/sidebarAtoms.ts";
import type { WorkspaceLayoutState } from "./persistence/types.ts";
import { DEFAULT_GLOBAL_LAYOUT, EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import {
  activePanelIdInSubSectionAtom,
  activeWorkspaceIdAtom,
  globalLayoutAtom,
  isSectionExpandedAtom,
  panelsInSubSectionAtom,
  removeWorkspaceLayoutAtom,
  sectionSizesAtom,
  switchActiveWorkspaceAtom,
  workspaceLayoutAtom,
} from "./sectionAtoms.ts";

function layoutWith(overrides: Partial<WorkspaceLayoutState>): WorkspaceLayoutState {
  return { ...EMPTY_WORKSPACE_LAYOUT, ...overrides };
}

beforeEach(() => {
  localStorage.clear();
});

describe("workspace layout scope + isolation", () => {
  it("flips per-workspace slices atomically on switch and keeps workspaces isolated", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-iso-a");
    store.set(
      workspaceLayoutAtom,
      layoutWith({
        placement: { "agent:1": "center", files: "left" },
        order: { center: ["agent:1"], left: ["files"] },
        activePanel: { center: "agent:1" },
        activeSubSection: "center",
      }),
    );
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual(["agent:1"]);

    store.set(activeWorkspaceIdAtom, "ws-iso-b");
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual([]);

    store.set(activeWorkspaceIdAtom, "ws-iso-a");
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual(["agent:1"]);
  });

  it("does not crash reading slices when no workspace is active", () => {
    const store = createStore();
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual([]);
    expect(store.get(isSectionExpandedAtom("center"))).toBe(true);
  });
});

describe("narrow read slices", () => {
  it("keeps a panel-list slice reference-stable and silent when an unrelated field changes", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-stable");
    store.set(workspaceLayoutAtom, layoutWith({ placement: { files: "left" }, order: { left: ["files"] } }));

    const slice = panelsInSubSectionAtom("left");
    let notifications = 0;
    const unsub = store.sub(slice, () => {
      notifications += 1;
    });
    const before = store.get(slice);

    store.set(workspaceLayoutAtom, (prev) => ({ ...prev, expanded: { ...prev.expanded, right: true } }));

    expect(store.get(slice)).toBe(before);
    expect(notifications).toBe(0);
    unsub();
  });

  it("activePanel falls back to the first open panel when unset or stale", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-active");
    store.set(
      workspaceLayoutAtom,
      layoutWith({ placement: { files: "left", changes: "left" }, order: { left: ["files", "changes"] } }),
    );
    expect(store.get(activePanelIdInSubSectionAtom("left"))).toBe("files");

    store.set(workspaceLayoutAtom, (prev) => ({ ...prev, activePanel: { left: "changes" } }));
    expect(store.get(activePanelIdInSubSectionAtom("left"))).toBe("changes");

    store.set(workspaceLayoutAtom, (prev) => ({ ...prev, activePanel: { left: "not-open" } }));
    expect(store.get(activePanelIdInSubSectionAtom("left"))).toBe("files");
  });

  it("center is always expanded; other sections honor the collapsed flag", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-exp");
    expect(store.get(isSectionExpandedAtom("center"))).toBe(true);
    expect(store.get(isSectionExpandedAtom("left"))).toBe(false);

    store.set(workspaceLayoutAtom, (prev) => ({ ...prev, expanded: { left: true } }));
    expect(store.get(isSectionExpandedAtom("left"))).toBe(true);
  });
});

describe("global slices are shared across workspaces", () => {
  it("sectionSizes are identical regardless of active workspace", () => {
    const store = createStore();
    store.set(globalLayoutAtom, { ...DEFAULT_GLOBAL_LAYOUT, sectionSizes: { left: 10, right: 15, bottom: 20 } });

    store.set(activeWorkspaceIdAtom, "ws-shared-1");
    expect(store.get(sectionSizesAtom)).toEqual({ left: 10, right: 15, bottom: 20 });

    store.set(activeWorkspaceIdAtom, "ws-shared-2");
    expect(store.get(sectionSizesAtom)).toEqual({ left: 10, right: 15, bottom: 20 });
  });

  it("sidebar atoms are writable slices of the global snapshot", () => {
    const store = createStore();
    store.set(sidebarWidthAtom, 333);
    store.set(sidebarCollapsedAtom, true);
    expect(store.get(sidebarWidthAtom)).toBe(333);
    expect(store.get(globalLayoutAtom).sidebarWidthPx).toBe(333);
    expect(store.get(globalLayoutAtom).sidebarCollapsed).toBe(true);
  });
});

describe("switch + remove", () => {
  it("seeds the default layout only on first visit", () => {
    const store = createStore();
    const seed = layoutWith({
      placement: { "agent:x": "center" },
      order: { center: ["agent:x"] },
      activePanel: { center: "agent:x" },
      activeSubSection: "center",
    });
    store.set(switchActiveWorkspaceAtom, { workspaceId: "ws-seed", defaultLayout: seed });
    expect(store.get(activeWorkspaceIdAtom)).toBe("ws-seed");
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual(["agent:x"]);

    // A later switch with a different default must not clobber the existing layout.
    store.set(switchActiveWorkspaceAtom, { workspaceId: "ws-seed", defaultLayout: EMPTY_WORKSPACE_LAYOUT });
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual(["agent:x"]);
  });

  it("removes a workspace's layout so re-entering it starts empty", () => {
    const store = createStore();
    store.set(switchActiveWorkspaceAtom, {
      workspaceId: "ws-del",
      defaultLayout: layoutWith({
        placement: { "agent:y": "center" },
        order: { center: ["agent:y"] },
        activeSubSection: "center",
      }),
    });
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual(["agent:y"]);

    // Delete is paired with navigating away; re-entering reads the dropped snapshot.
    store.set(activeWorkspaceIdAtom, "ws-other");
    store.set(removeWorkspaceLayoutAtom, { workspaceId: "ws-del" });
    store.set(activeWorkspaceIdAtom, "ws-del");
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual([]);
  });
});
