import { createStore } from "jotai";
import { Circle } from "lucide-react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import {
  createPanelStore,
  didZenImplyFocusModeAtom,
  focusModeActiveAtom,
  focusModeSavedVisibilityAtom,
  isSideVisibleAtom,
  isZoneVisibleAtom,
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
