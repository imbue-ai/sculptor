import { createStore } from "jotai";
import { Circle } from "lucide-react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import type { PanelDragState } from "~/components/panels/atoms.ts";
import {
  activePanelIdInZoneAtom,
  activePanelPerZoneAtom,
  computeDisplayedPanelIds,
  createPanelStore,
  didZenImplyFocusModeAtom,
  displayedPanelIdsAtom,
  focusedZoneAtom,
  focusModeActiveAtom,
  focusModeSavedVisibilityAtom,
  ghostPanelIdAtom,
  isDropTargetAtom,
  isPanelDragActiveAtom,
  isSideVisibleAtom,
  isZoneFocusedAtom,
  isZoneVisibleAtom,
  panelDragStateAtom,
  panelEnabledAtom,
  panelShortcutsAtom,
  panelsInZoneAtom,
  savedSideVisibilityAtom,
  zenModeActiveAtom,
  zoneAssignmentsAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";

// ── Test fixtures ────────────────────────────────────────────────────

const TEST_PANELS: ReadonlyArray<PanelDefinition> = [
  {
    id: "info",
    displayName: "Info",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-left",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "terminal",
    displayName: "Terminal",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
  {
    id: "changes",
    displayName: "Changes",
    description: "Test panel",
    icon: Circle,
    defaultZone: "top-right",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
];

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

// ── isSideVisibleAtom ────────────────────────────────────────────────

describe("isSideVisibleAtom", () => {
  it("returns true when any zone in the side is visible", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(isSideVisibleAtom("right"))).toBe(true);
  });

  it("returns false when all zones in the side are hidden", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(zoneVisibilityAtom, { "top-right": false, "bottom-right": false });
    expect(store.get(isSideVisibleAtom("right"))).toBe(false);
  });

  it("returns false for a side with no panels assigned", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    // Left side has "info" in top-left, but let's move it away
    store.set(zoneAssignmentsAtom, { info: "top-right", terminal: "bottom", changes: "top-right" });
    store.set(zoneVisibilityAtom, { "top-left": true, "top-right": true, bottom: true });
    // Left side zones are "visible" in the atom but have no panels → should be false
    expect(store.get(isSideVisibleAtom("left"))).toBe(false);
  });

  it("returns true for left side when only bottom-left is visible", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(zoneAssignmentsAtom, { info: "bottom-left", terminal: "bottom", changes: "top-right" });
    store.set(zoneVisibilityAtom, { "top-left": false, "bottom-left": true, bottom: true, "top-right": true });
    expect(store.get(isSideVisibleAtom("left"))).toBe(true);
  });
});

// ── savedSideVisibilityAtom ──────────────────────────────────────────

describe("savedSideVisibilityAtom", () => {
  it("defaults to empty object", () => {
    const store = createStore();
    expect(store.get(savedSideVisibilityAtom)).toEqual({});
  });

  it("stores per-side snapshots independently", () => {
    const store = createStore();
    store.set(savedSideVisibilityAtom, {
      right: { "top-right": true, "bottom-right": false },
      left: { "top-left": true },
    });
    const saved = store.get(savedSideVisibilityAtom);
    expect(saved.right).toEqual({ "top-right": true, "bottom-right": false });
    expect(saved.left).toEqual({ "top-left": true });
  });
});

// ── Zen mode atoms ──────────────────────────────────────────────────

describe("zenModeActiveAtom", () => {
  it("defaults to false", () => {
    const store = createStore();
    expect(store.get(zenModeActiveAtom)).toBe(false);
  });

  it("can be toggled", () => {
    const store = createStore();
    store.set(zenModeActiveAtom, true);
    expect(store.get(zenModeActiveAtom)).toBe(true);
    store.set(zenModeActiveAtom, false);
    expect(store.get(zenModeActiveAtom)).toBe(false);
  });
});

describe("didZenImplyFocusModeAtom", () => {
  it("defaults to false", () => {
    const store = createStore();
    expect(store.get(didZenImplyFocusModeAtom)).toBe(false);
  });

  it("can be set independently", () => {
    const store = createStore();
    store.set(didZenImplyFocusModeAtom, true);
    expect(store.get(didZenImplyFocusModeAtom)).toBe(true);
  });
});

// ── Focus mode atoms ────────────────────────────────────────────────

describe("focusModeActiveAtom", () => {
  it("defaults to false", () => {
    const store = createStore();
    expect(store.get(focusModeActiveAtom)).toBe(false);
  });
});

describe("focusModeSavedVisibilityAtom", () => {
  it("defaults to empty object", () => {
    const store = createStore();
    expect(store.get(focusModeSavedVisibilityAtom)).toEqual({});
  });

  it("stores zone visibility snapshot", () => {
    const store = createStore();
    store.set(focusModeSavedVisibilityAtom, {
      "top-left": true,
      "top-right": true,
      bottom: false,
    });
    const saved = store.get(focusModeSavedVisibilityAtom);
    expect(saved["top-left"]).toBe(true);
    expect(saved["bottom"]).toBe(false);
  });
});

// ── panelEnabledAtom ─────────────────────────────────────────────────

describe("panel enabled state", () => {
  it("disabling a non-builtin panel removes it from panelsInZoneAtom", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(panelsInZoneAtom("top-left"))).toEqual(["info"]);
    store.set(panelEnabledAtom, { info: false });
    expect(store.get(panelsInZoneAtom("top-left"))).toEqual([]);
  });

  it("disabling the only panel in a zone hides the zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(isZoneVisibleAtom("top-left"))).toBe(true);
    store.set(panelEnabledAtom, { info: false });
    expect(store.get(isZoneVisibleAtom("top-left"))).toBe(false);
  });

  it("re-enabling restores the panel in its previously assigned zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(panelEnabledAtom, { info: false });
    expect(store.get(panelsInZoneAtom("top-left"))).toEqual([]);
    store.set(panelEnabledAtom, { info: true });
    expect(store.get(panelsInZoneAtom("top-left"))).toEqual(["info"]);
  });

  it("ignores stored disabled state for builtin panels", () => {
    const builtinPanels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, isBuiltin: true } : p,
    );
    const store = createPanelStore(builtinPanels, { useDefaultLayout: true });
    store.set(panelEnabledAtom, { info: false });
    expect(store.get(panelsInZoneAtom("top-left"))).toEqual(["info"]);
  });

  it("excludes disabled panels from panelShortcutsAtom", () => {
    const panelsWithShortcut: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Cmd+1" } : p,
    );
    const store = createPanelStore(panelsWithShortcut, { useDefaultLayout: true });
    expect(store.get(panelShortcutsAtom).info).toBe("Cmd+1");
    store.set(panelEnabledAtom, { info: false });
    expect(store.get(panelShortcutsAtom).info).toBeUndefined();
  });
});

// ── computeDisplayedPanelIds ─────────────────────────────────────────

describe("computeDisplayedPanelIds", () => {
  const panelIds = ["a", "b", "c"];

  it("returns the input reference when no drag is in flight", () => {
    expect(computeDisplayedPanelIds({ zone: "top-left", panelIds, drag: null })).toBe(panelIds);
  });

  it("returns the input reference for a zone the drag does not touch", () => {
    const drag: PanelDragState = { activePanelId: "x", sourceZone: "bottom", targetZone: "top-right", insertIndex: 0 };
    expect(computeDisplayedPanelIds({ zone: "top-left", panelIds, drag })).toBe(panelIds);
  });

  it("removes the dragged panel from the source zone", () => {
    const drag: PanelDragState = {
      activePanelId: "b",
      sourceZone: "top-left",
      targetZone: "top-right",
      insertIndex: 0,
    };
    expect(computeDisplayedPanelIds({ zone: "top-left", panelIds, drag })).toEqual(["a", "c"]);
  });

  it("inserts the ghost into the target zone at the insertion index", () => {
    const drag: PanelDragState = { activePanelId: "x", sourceZone: "bottom", targetZone: "top-left", insertIndex: 1 };
    expect(computeDisplayedPanelIds({ zone: "top-left", panelIds, drag })).toEqual(["a", "x", "b", "c"]);
  });

  it("relocates within the zone when dragging over the same zone", () => {
    const drag: PanelDragState = {
      activePanelId: "a",
      sourceZone: "top-left",
      targetZone: "top-left",
      insertIndex: 2,
    };
    expect(computeDisplayedPanelIds({ zone: "top-left", panelIds, drag })).toEqual(["b", "c", "a"]);
  });

  it("clamps an out-of-range insertion index", () => {
    const drag: PanelDragState = { activePanelId: "x", sourceZone: "bottom", targetZone: "top-left", insertIndex: 99 };
    expect(computeDisplayedPanelIds({ zone: "top-left", panelIds, drag })).toEqual(["a", "b", "c", "x"]);
  });
});

// ── Per-zone drag-state slices ───────────────────────────────────────
// These pin the notification contract the drag perf depends on: a drag-state
// change must only notify the zones it actually affects.

describe("per-zone drag-state slices", () => {
  // Default layout: info → top-left, terminal → bottom, changes → top-right.
  const dragInfoToTopRight = (insertIndex: number): PanelDragState => ({
    activePanelId: "info",
    sourceZone: "top-left",
    targetZone: "top-right",
    insertIndex,
  });

  it("does not notify displayedPanelIds subscribers of uninvolved zones", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(displayedPanelIdsAtom("bottom"), () => {
      notifications += 1;
    });
    store.set(panelDragStateAtom, dragInfoToTopRight(0));
    store.set(panelDragStateAtom, dragInfoToTopRight(1));
    store.set(panelDragStateAtom, null);
    expect(notifications).toBe(0);
  });

  it("does not notify the source zone's displayedPanelIds at drag start", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(displayedPanelIdsAtom("top-left"), () => {
      notifications += 1;
    });
    // Drag start targets the source zone at the panel's own index — the
    // displayed list is unchanged, so subscribers must not be notified.
    store.set(panelDragStateAtom, {
      activePanelId: "info",
      sourceZone: "top-left",
      targetZone: "top-left",
      insertIndex: 0,
    });
    expect(notifications).toBe(0);
  });

  it("notifies the target zone's displayedPanelIds only when its list changes", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(displayedPanelIdsAtom("top-right"), () => {
      notifications += 1;
    });
    store.set(panelDragStateAtom, dragInfoToTopRight(0));
    expect(store.get(displayedPanelIdsAtom("top-right"))).toEqual(["info", "changes"]);
    expect(notifications).toBe(1);
    // Same target and index in a fresh state object — recomputes to an equal
    // list, so no notification.
    store.set(panelDragStateAtom, dragInfoToTopRight(0));
    expect(notifications).toBe(1);
    store.set(panelDragStateAtom, dragInfoToTopRight(1));
    expect(store.get(displayedPanelIdsAtom("top-right"))).toEqual(["changes", "info"]);
    expect(notifications).toBe(2);
  });

  it("isDropTargetAtom flips once per zone entry, not per insertion-index change", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(isDropTargetAtom("top-right"), () => {
      notifications += 1;
    });
    store.set(panelDragStateAtom, dragInfoToTopRight(0));
    expect(store.get(isDropTargetAtom("top-right"))).toBe(true);
    store.set(panelDragStateAtom, dragInfoToTopRight(1));
    expect(notifications).toBe(1);
    store.set(panelDragStateAtom, null);
    expect(store.get(isDropTargetAtom("top-right"))).toBe(false);
    expect(notifications).toBe(2);
  });

  it("isDropTargetAtom stays false for the source zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(panelDragStateAtom, {
      activePanelId: "info",
      sourceZone: "top-left",
      targetZone: "top-left",
      insertIndex: 0,
    });
    expect(store.get(isDropTargetAtom("top-left"))).toBe(false);
  });

  it("ghostPanelIdAtom reports the dragged id only while the zone is targeted", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(ghostPanelIdAtom("top-right"), () => {
      notifications += 1;
    });
    store.set(panelDragStateAtom, dragInfoToTopRight(0));
    expect(store.get(ghostPanelIdAtom("top-right"))).toBe("info");
    store.set(panelDragStateAtom, dragInfoToTopRight(1));
    expect(notifications).toBe(1);
    store.set(panelDragStateAtom, null);
    expect(store.get(ghostPanelIdAtom("top-right"))).toBe(null);
    expect(notifications).toBe(2);
  });

  it("isPanelDragActiveAtom flips only at drag start and end", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(isPanelDragActiveAtom, () => {
      notifications += 1;
    });
    store.set(panelDragStateAtom, dragInfoToTopRight(0));
    store.set(panelDragStateAtom, dragInfoToTopRight(1));
    store.set(panelDragStateAtom, dragInfoToTopRight(2));
    expect(notifications).toBe(1);
    store.set(panelDragStateAtom, null);
    expect(notifications).toBe(2);
  });
});

// ── activePanelIdInZoneAtom ──────────────────────────────────────────

describe("activePanelIdInZoneAtom", () => {
  it("returns the stored active panel when it is in the zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(activePanelIdInZoneAtom("top-left"))).toBe("info");
  });

  it("falls back to the zone's first panel when the stored active panel left the zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(activePanelPerZoneAtom, { "top-left": "changes" });
    expect(store.get(activePanelIdInZoneAtom("top-left"))).toBe("info");
  });

  it("falls back to the zone's first panel when no active panel is stored", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(activePanelPerZoneAtom, {});
    expect(store.get(activePanelIdInZoneAtom("top-left"))).toBe("info");
  });

  it("returns undefined for an empty zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(activePanelIdInZoneAtom("bottom-left"))).toBeUndefined();
  });
});

// ── isZoneFocusedAtom ────────────────────────────────────────────────

describe("isZoneFocusedAtom", () => {
  it("tracks the focused zone", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(isZoneFocusedAtom("center"))).toBe(false);
    store.set(focusedZoneAtom, "center");
    expect(store.get(isZoneFocusedAtom("center"))).toBe(true);
  });

  it("does not notify uninvolved zones when focus moves between two others", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    let notifications = 0;
    store.sub(isZoneFocusedAtom("top-left"), () => {
      notifications += 1;
    });
    store.set(focusedZoneAtom, "center");
    store.set(focusedZoneAtom, "top-right");
    expect(notifications).toBe(0);
  });
});

describe("panelShortcutsAtom round-trip via userConfig.keybindings", () => {
  it("returns an empty map when every panel has an empty defaultShortcut and no overrides", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(panelShortcutsAtom)).toEqual({});
  });

  it("flows a userConfig override into the result map", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    store.set(userConfigAtom, { keybindings: { panel_info: "Meta+E" } } as unknown as UserConfig);
    expect(store.get(panelShortcutsAtom).info).toBe("Meta+E");
  });

  it("treats an explicit null override as no shortcut (entry absent)", () => {
    const panelsWithDefault: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Cmd+1" } : p,
    );
    const store = createPanelStore(panelsWithDefault, { useDefaultLayout: true });
    expect(store.get(panelShortcutsAtom).info).toBe("Cmd+1");
    store.set(userConfigAtom, { keybindings: { panel_info: null } } as unknown as UserConfig);
    expect(store.get(panelShortcutsAtom).info).toBeUndefined();
  });
});
