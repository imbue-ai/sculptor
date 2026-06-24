import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import {
  activeSectionRingVisibleAtom,
  displayedPanelIdsAtom,
  draggedPanelIdAtom,
  ghostPanelIdAtom,
  isDropTargetAtom,
  isRingVisibleAtom,
  maximizedSectionAtom,
  panelDragStateAtom,
} from "./transientAtoms.ts";

beforeEach(() => {
  localStorage.clear();
});

describe("maximized section", () => {
  it("defaults to null and is a plain settable atom", () => {
    const store = createStore();
    expect(store.get(maximizedSectionAtom)).toBeNull();
    store.set(maximizedSectionAtom, "center");
    expect(store.get(maximizedSectionAtom)).toBe("center");
  });
});

describe("drag preview", () => {
  it("draggedPanelIdAtom stays stable while only the insertion index changes", () => {
    const store = createStore();
    store.set(panelDragStateAtom, { panelId: "a", from: "left", to: "center", index: 0 });

    let notifications = 0;
    const unsub = store.sub(draggedPanelIdAtom, () => {
      notifications += 1;
    });
    expect(store.get(draggedPanelIdAtom)).toBe("a");

    store.set(panelDragStateAtom, { panelId: "a", from: "left", to: "center", index: 1 });
    store.set(panelDragStateAtom, { panelId: "a", from: "left", to: "center", index: 2 });

    expect(store.get(draggedPanelIdAtom)).toBe("a");
    expect(notifications).toBe(0);
    unsub();
  });

  it("isDropTargetAtom / ghostPanelIdAtom are true only for the current target", () => {
    const store = createStore();
    store.set(panelDragStateAtom, { panelId: "x", from: "right", to: "center", index: 0 });
    expect(store.get(isDropTargetAtom("center"))).toBe(true);
    expect(store.get(isDropTargetAtom("left"))).toBe(false);
    expect(store.get(ghostPanelIdAtom("center"))).toBe("x");
    expect(store.get(ghostPanelIdAtom("left"))).toBeNull();
  });

  it("displayedPanelIdsAtom splices the ghost in at the insertion index", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-drag");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { a: "center", b: "center" },
      order: { center: ["a", "b"] },
    });

    // No drag: passthrough of the open panels.
    expect(store.get(displayedPanelIdsAtom("center"))).toEqual(["a", "b"]);

    // Dragging a foreign panel into the middle.
    store.set(panelDragStateAtom, { panelId: "x", from: "right", to: "center", index: 1 });
    expect(store.get(displayedPanelIdsAtom("center"))).toEqual(["a", "x", "b"]);

    // Dragging an existing panel further right (it is removed before re-insertion).
    store.set(panelDragStateAtom, { panelId: "a", from: "center", to: "center", index: 2 });
    expect(store.get(displayedPanelIdsAtom("center"))).toEqual(["b", "a"]);
  });
});

describe("active-section ring", () => {
  it("isRingVisibleAtom is true only for the active sub-section while the ring is visible", () => {
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-ring");
    store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, activeSubSection: "center" });

    expect(store.get(isRingVisibleAtom("center"))).toBe(false);

    store.set(activeSectionRingVisibleAtom, true);
    expect(store.get(isRingVisibleAtom("center"))).toBe(true);
    expect(store.get(isRingVisibleAtom("left"))).toBe(false);

    store.set(activeSectionRingVisibleAtom, false);
    expect(store.get(isRingVisibleAtom("center"))).toBe(false);
  });
});
