import { act, fireEvent, render, renderHook } from "@testing-library/react";
import type { createStore } from "jotai";
import { Provider } from "jotai";
import { Circle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  activePanelPerZoneAtom,
  createPanelStore,
  didZenImplyFocusModeAtom,
  focusModeActiveAtom,
  focusModeSavedVisibilityAtom,
  panelEnabledAtom,
  panelsInZoneAtom,
  savedSideVisibilityAtom,
  zenModeActiveAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import {
  useFocusMode,
  usePanelEnabled,
  usePanelKeyboardShortcuts,
  useSideToggle,
  useZenMode,
} from "~/components/panels/hooks.ts";
import { PanelRegistryProvider } from "~/components/panels/PanelRegistryProvider";
import type { LayoutSide, PanelDefinition } from "~/components/panels/types.ts";
import { ZONE_IDS } from "~/components/panels/types.ts";

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
    id: "cost",
    displayName: "Cost",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom-left",
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
  {
    id: "actions",
    displayName: "Actions",
    description: "Test panel",
    icon: Circle,
    defaultZone: "bottom-right",
    defaultShortcut: "",
    component: () => createElement("div"),
  },
];

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

const renderSideToggle = (
  side: LayoutSide,
  store: ReturnType<typeof createStore>,
): ReturnType<typeof renderHook<ReturnType<typeof useSideToggle>, unknown>> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <PanelRegistryProvider panels={TEST_PANELS}>{children}</PanelRegistryProvider>
    </Provider>
  );
  return renderHook(() => useSideToggle(side), { wrapper });
};

const createDefaultStore = (): ReturnType<typeof createStore> =>
  createPanelStore(TEST_PANELS, { useDefaultLayout: true });

describe("useSideToggle", () => {
  describe("isVisible", () => {
    it("returns true when the side has at least one visible zone", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("right", store);
      expect(result.current.isVisible).toBe(true);
    });

    it("returns false when all zones in the side are hidden", () => {
      const store = createDefaultStore();
      store.set(zoneVisibilityAtom, (prev) => ({
        ...prev,
        "top-right": false,
        "bottom-right": false,
      }));
      const { result } = renderSideToggle("right", store);
      expect(result.current.isVisible).toBe(false);
    });
  });

  describe("toggle — hiding a side", () => {
    it("hides all zones in the right side when toggled off", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("right", store);

      act(() => result.current.toggle());

      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-right"]).toBe(false);
      expect(vis["bottom-right"]).toBe(false);
    });

    it("hides the bottom zone when toggled off", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("bottom", store);

      act(() => result.current.toggle());

      expect(store.get(zoneVisibilityAtom)["bottom"]).toBe(false);
    });

    it("saves a visibility snapshot before hiding", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("right", store);

      act(() => result.current.toggle());

      const saved = store.get(savedSideVisibilityAtom);
      expect(saved.right).toBeDefined();
      expect(saved.right!["top-right"]).toBe(true);
    });

    it("does not affect zones outside the toggled side", () => {
      const store = createDefaultStore();
      const visBefore = { ...store.get(zoneVisibilityAtom) };
      const { result } = renderSideToggle("right", store);

      act(() => result.current.toggle());

      const visAfter = store.get(zoneVisibilityAtom);
      // Left and bottom zones unchanged
      expect(visAfter["top-left"]).toBe(visBefore["top-left"]);
      expect(visAfter["bottom"]).toBe(visBefore["bottom"]);
    });
  });

  describe("toggle — restoring a side", () => {
    it("restores saved per-zone visibility when toggled back on", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("right", store);

      // Hide
      act(() => result.current.toggle());
      expect(result.current.isVisible).toBe(false);

      // Restore
      act(() => result.current.toggle());
      expect(result.current.isVisible).toBe(true);

      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-right"]).toBe(true);
    });

    it("defaults to first zone when no saved state exists", () => {
      const store = createDefaultStore();
      // Manually hide right zones without saving a snapshot
      store.set(zoneVisibilityAtom, (prev) => ({
        ...prev,
        "top-right": false,
        "bottom-right": false,
      }));

      const { result } = renderSideToggle("right", store);
      expect(result.current.isVisible).toBe(false);

      act(() => result.current.toggle());

      const vis = store.get(zoneVisibilityAtom);
      expect(vis["top-right"]).toBe(true);
    });

    it("clears saved snapshot after restoring", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("right", store);

      act(() => result.current.toggle()); // hide
      expect(store.get(savedSideVisibilityAtom).right).toBeDefined();

      act(() => result.current.toggle()); // restore
      expect(store.get(savedSideVisibilityAtom).right).toBeUndefined();
    });
  });

  describe("toggle — round-trip scenarios", () => {
    it("preserves mixed visibility through a toggle round-trip", () => {
      const store = createDefaultStore();
      // Set up mixed state: top-right visible, bottom-right hidden
      store.set(zoneVisibilityAtom, (prev) => ({
        ...prev,
        "top-right": true,
        "bottom-right": false,
      }));

      const { result } = renderSideToggle("right", store);

      // Hide
      act(() => result.current.toggle());
      expect(store.get(zoneVisibilityAtom)["top-right"]).toBe(false);
      expect(store.get(zoneVisibilityAtom)["bottom-right"]).toBe(false);

      // Restore — should get back the mixed state
      act(() => result.current.toggle());
      expect(store.get(zoneVisibilityAtom)["top-right"]).toBe(true);
      expect(store.get(zoneVisibilityAtom)["bottom-right"]).toBe(false);
    });

    it("handles multiple toggle cycles correctly", () => {
      const store = createDefaultStore();
      const { result } = renderSideToggle("bottom", store);

      // Cycle 1
      act(() => result.current.toggle()); // hide
      expect(result.current.isVisible).toBe(false);
      act(() => result.current.toggle()); // show
      expect(result.current.isVisible).toBe(true);

      // Cycle 2
      act(() => result.current.toggle()); // hide
      expect(result.current.isVisible).toBe(false);
      act(() => result.current.toggle()); // show
      expect(result.current.isVisible).toBe(true);
    });

    it("sets activePanelPerZone for zones that have no active panel when restoring", () => {
      const store = createDefaultStore();

      // Clear the active panel for the bottom zone to simulate the bug scenario:
      // the zone has panels assigned but no active panel selected.
      store.set(activePanelPerZoneAtom, (prev) => {
        const next = { ...prev };
        delete next["bottom"];
        return next;
      });
      // Hide the bottom zone (no saved snapshot)
      store.set(zoneVisibilityAtom, (prev) => ({ ...prev, bottom: false }));

      const { result } = renderSideToggle("bottom", store);
      expect(result.current.isVisible).toBe(false);

      // Toggle on — should restore visibility AND set an active panel
      act(() => result.current.toggle());

      expect(result.current.isVisible).toBe(true);
      const activePanel = store.get(activePanelPerZoneAtom)["bottom"];
      expect(activePanel).toBeDefined();
      expect(activePanel).toBe("terminal"); // first (only) panel in the bottom zone
    });

    it("allows toggling different sides independently", () => {
      const store = createDefaultStore();
      const rightToggle = renderSideToggle("right", store);
      const bottomToggle = renderSideToggle("bottom", store);

      // Hide right
      act(() => rightToggle.result.current.toggle());
      expect(rightToggle.result.current.isVisible).toBe(false);
      expect(bottomToggle.result.current.isVisible).toBe(true);

      // Hide bottom
      act(() => bottomToggle.result.current.toggle());
      expect(rightToggle.result.current.isVisible).toBe(false);
      expect(bottomToggle.result.current.isVisible).toBe(false);

      // Restore right only
      act(() => rightToggle.result.current.toggle());
      expect(rightToggle.result.current.isVisible).toBe(true);
      expect(bottomToggle.result.current.isVisible).toBe(false);
    });
  });
});

const renderFocusMode = (
  store: ReturnType<typeof createStore>,
): ReturnType<typeof renderHook<ReturnType<typeof useFocusMode>, unknown>> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <PanelRegistryProvider panels={TEST_PANELS}>{children}</PanelRegistryProvider>
    </Provider>
  );
  return renderHook(() => useFocusMode(), { wrapper });
};

const renderZenMode = (
  store: ReturnType<typeof createStore>,
): ReturnType<typeof renderHook<ReturnType<typeof useZenMode>, unknown>> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <PanelRegistryProvider panels={TEST_PANELS}>{children}</PanelRegistryProvider>
    </Provider>
  );
  return renderHook(() => useZenMode(), { wrapper });
};

/** Returns true if any zone has visibility set to true. */
const hasAnyVisibleZone = (store: ReturnType<typeof createStore>): boolean => {
  const vis = store.get(zoneVisibilityAtom);
  return ZONE_IDS.some((z) => vis[z] === true);
};

describe("useFocusMode", () => {
  describe("entering focus mode", () => {
    it("sets focusModeActive to true", () => {
      const store = createDefaultStore();
      const { result } = renderFocusMode(store);

      act(() => result.current.toggleFocusMode());

      expect(result.current.isFocusModeActive).toBe(true);
      expect(store.get(focusModeActiveAtom)).toBe(true);
    });

    it("hides all zones", () => {
      const store = createDefaultStore();
      const { result } = renderFocusMode(store);

      // Verify zones are visible initially
      expect(hasAnyVisibleZone(store)).toBe(true);

      act(() => result.current.toggleFocusMode());

      expect(hasAnyVisibleZone(store)).toBe(false);
    });

    it("saves zone visibility snapshot", () => {
      const store = createDefaultStore();
      const { result } = renderFocusMode(store);

      act(() => result.current.toggleFocusMode());

      const saved = store.get(focusModeSavedVisibilityAtom);
      // The saved state should have at least some true values from the default layout
      expect(Object.values(saved).some(Boolean)).toBe(true);
    });
  });

  describe("exiting focus mode", () => {
    it("restores zone visibility", () => {
      const store = createDefaultStore();
      const visBefore = { ...store.get(zoneVisibilityAtom) };
      const { result } = renderFocusMode(store);

      // Enter then exit
      act(() => result.current.toggleFocusMode());
      expect(hasAnyVisibleZone(store)).toBe(false);

      act(() => result.current.toggleFocusMode());

      // Zones that were visible before should be visible again
      const visAfter = store.get(zoneVisibilityAtom);
      for (const zoneId of ZONE_IDS) {
        if (visBefore[zoneId]) {
          expect(visAfter[zoneId]).toBe(true);
        }
      }
    });

    it("clears saved visibility", () => {
      const store = createDefaultStore();
      const { result } = renderFocusMode(store);

      act(() => result.current.toggleFocusMode());
      expect(Object.keys(store.get(focusModeSavedVisibilityAtom)).length).toBeGreaterThan(0);

      act(() => result.current.toggleFocusMode());
      expect(store.get(focusModeSavedVisibilityAtom)).toEqual({});
    });

    it("also exits zen mode when exiting focus mode", () => {
      const store = createDefaultStore();
      // Simulate zen mode being active
      store.set(zenModeActiveAtom, true);
      store.set(didZenImplyFocusModeAtom, true);
      store.set(focusModeActiveAtom, true);

      const { result } = renderFocusMode(store);
      act(() => result.current.toggleFocusMode());

      expect(store.get(zenModeActiveAtom)).toBe(false);
      expect(store.get(didZenImplyFocusModeAtom)).toBe(false);
    });
  });
});

describe("useZenMode", () => {
  describe("entering zen mode from nothing active", () => {
    it("activates zen mode", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      act(() => result.current.toggleZenMode());

      expect(result.current.isZenModeActive).toBe(true);
      expect(store.get(zenModeActiveAtom)).toBe(true);
    });

    it("also activates focus mode", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      act(() => result.current.toggleZenMode());

      expect(store.get(focusModeActiveAtom)).toBe(true);
    });

    it("sets didZenImplyFocusMode to true", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      act(() => result.current.toggleZenMode());

      expect(store.get(didZenImplyFocusModeAtom)).toBe(true);
    });

    it("hides all zones", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      act(() => result.current.toggleZenMode());

      expect(hasAnyVisibleZone(store)).toBe(false);
    });
  });

  describe("entering zen mode when focus mode is already active", () => {
    it("does not set didZenImplyFocusMode", () => {
      const store = createDefaultStore();

      // Enter focus mode first
      const focusHook = renderFocusMode(store);
      act(() => focusHook.result.current.toggleFocusMode());
      expect(store.get(focusModeActiveAtom)).toBe(true);

      // Now enter zen mode
      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode());

      expect(store.get(zenModeActiveAtom)).toBe(true);
      expect(store.get(didZenImplyFocusModeAtom)).toBe(false);
    });
  });

  describe("exiting zen mode (Cmd+Shift+\\)", () => {
    it("deactivates zen mode", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      act(() => result.current.toggleZenMode()); // enter
      act(() => result.current.toggleZenMode()); // exit

      expect(result.current.isZenModeActive).toBe(false);
      expect(store.get(zenModeActiveAtom)).toBe(false);
    });

    it("also exits focus mode when zen implied it", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      act(() => result.current.toggleZenMode()); // enter (implies focus)
      expect(store.get(focusModeActiveAtom)).toBe(true);
      expect(store.get(didZenImplyFocusModeAtom)).toBe(true);

      act(() => result.current.toggleZenMode()); // exit

      expect(store.get(focusModeActiveAtom)).toBe(false);
      expect(store.get(didZenImplyFocusModeAtom)).toBe(false);
    });

    it("preserves focus mode when it was active before zen", () => {
      const store = createDefaultStore();

      // Enter focus mode first
      const focusHook = renderFocusMode(store);
      act(() => focusHook.result.current.toggleFocusMode());

      // Enter then exit zen mode
      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode()); // enter
      act(() => zenHook.result.current.toggleZenMode()); // exit

      // Focus mode should still be active
      expect(store.get(focusModeActiveAtom)).toBe(true);
      expect(store.get(zenModeActiveAtom)).toBe(false);
    });

    it("restores zone visibility when zen implied focus mode", () => {
      const store = createDefaultStore();
      const visBefore = { ...store.get(zoneVisibilityAtom) };

      const { result } = renderZenMode(store);
      act(() => result.current.toggleZenMode()); // enter
      expect(hasAnyVisibleZone(store)).toBe(false);

      act(() => result.current.toggleZenMode()); // exit

      // Zones that were visible before should be restored
      const visAfter = store.get(zoneVisibilityAtom);
      for (const zoneId of ZONE_IDS) {
        if (visBefore[zoneId]) {
          expect(visAfter[zoneId]).toBe(true);
        }
      }
    });
  });

  describe("exiting zen mode via focus mode toggle (Cmd+\\)", () => {
    it("exits both zen and focus mode", () => {
      const store = createDefaultStore();

      // Enter zen mode (which implies focus mode)
      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode());
      expect(store.get(zenModeActiveAtom)).toBe(true);
      expect(store.get(focusModeActiveAtom)).toBe(true);

      // Exit via focus mode toggle
      const focusHook = renderFocusMode(store);
      act(() => focusHook.result.current.toggleFocusMode());

      expect(store.get(zenModeActiveAtom)).toBe(false);
      expect(store.get(focusModeActiveAtom)).toBe(false);
      expect(store.get(didZenImplyFocusModeAtom)).toBe(false);
    });

    it("restores zone visibility", () => {
      const store = createDefaultStore();
      const visBefore = { ...store.get(zoneVisibilityAtom) };

      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode());

      const focusHook = renderFocusMode(store);
      act(() => focusHook.result.current.toggleFocusMode());

      const visAfter = store.get(zoneVisibilityAtom);
      for (const zoneId of ZONE_IDS) {
        if (visBefore[zoneId]) {
          expect(visAfter[zoneId]).toBe(true);
        }
      }
    });
  });

  describe("panel toggles in zen mode update saved state", () => {
    it("useSideToggle.toggle() works in zen mode and stays in zen mode", () => {
      const store = createDefaultStore();

      // Enter zen mode (all zones hidden)
      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode());
      expect(store.get(zenModeActiveAtom)).toBe(true);
      expect(store.get(focusModeActiveAtom)).toBe(true);

      // Toggle the bottom side — should show it and stay in zen mode
      const sideToggle = renderSideToggle("bottom", store);
      act(() => sideToggle.result.current.toggle());

      // Bottom zone should now be visible
      expect(store.get(zoneVisibilityAtom)["bottom"]).toBe(true);
      // Zen and focus mode still active
      expect(store.get(zenModeActiveAtom)).toBe(true);
      expect(store.get(focusModeActiveAtom)).toBe(true);
    });

    it("panel toggled open in zen mode stays open after exiting zen", () => {
      const store = createDefaultStore();

      // Bottom is visible before zen
      expect(store.get(zoneVisibilityAtom)["bottom"]).toBe(true);

      // Enter zen mode (all zones hidden)
      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode());
      expect(store.get(zoneVisibilityAtom)["bottom"]).toBe(false);

      // Toggle bottom open during zen mode
      const sideToggle = renderSideToggle("bottom", store);
      act(() => sideToggle.result.current.toggle());
      expect(store.get(zoneVisibilityAtom)["bottom"]).toBe(true);

      // Exit zen mode
      act(() => zenHook.result.current.toggleZenMode());

      // Bottom should still be visible (the toggle persisted via saved state)
      expect(store.get(zoneVisibilityAtom)["bottom"]).toBe(true);
      expect(store.get(zenModeActiveAtom)).toBe(false);
      expect(store.get(focusModeActiveAtom)).toBe(false);
    });

    it("panel toggled closed in zen mode stays closed after exiting zen", () => {
      const store = createDefaultStore();

      // Right side is visible before zen
      expect(store.get(zoneVisibilityAtom)["top-right"]).toBe(true);

      // Enter zen mode (all zones hidden)
      const zenHook = renderZenMode(store);
      act(() => zenHook.result.current.toggleZenMode());

      // Toggle right open, then close it again during zen mode
      const sideToggle = renderSideToggle("right", store);
      act(() => sideToggle.result.current.toggle()); // open
      expect(store.get(zoneVisibilityAtom)["top-right"]).toBe(true);
      act(() => sideToggle.result.current.toggle()); // close
      expect(store.get(zoneVisibilityAtom)["top-right"]).toBe(false);

      // Exit zen mode
      act(() => zenHook.result.current.toggleZenMode());

      // Right should be closed (user's last action was to close it)
      expect(store.get(zoneVisibilityAtom)["top-right"]).toBe(false);
    });
  });

  describe("round-trip scenarios", () => {
    it("handles multiple zen mode toggle cycles", () => {
      const store = createDefaultStore();
      const { result } = renderZenMode(store);

      // Cycle 1
      act(() => result.current.toggleZenMode());
      expect(result.current.isZenModeActive).toBe(true);
      act(() => result.current.toggleZenMode());
      expect(result.current.isZenModeActive).toBe(false);

      // Cycle 2
      act(() => result.current.toggleZenMode());
      expect(result.current.isZenModeActive).toBe(true);
      act(() => result.current.toggleZenMode());
      expect(result.current.isZenModeActive).toBe(false);

      // All state should be clean
      expect(store.get(focusModeActiveAtom)).toBe(false);
      expect(store.get(didZenImplyFocusModeAtom)).toBe(false);
    });
  });
});

const renderPanelEnabled = (
  store: ReturnType<typeof createStore>,
  panels: ReadonlyArray<PanelDefinition> = TEST_PANELS,
): ReturnType<typeof renderHook<ReturnType<typeof usePanelEnabled>, unknown>> => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <PanelRegistryProvider panels={panels}>{children}</PanelRegistryProvider>
    </Provider>
  );
  return renderHook(() => usePanelEnabled(), { wrapper });
};

describe("usePanelEnabled", () => {
  it("setEnabled persists state and updates panelsInZoneAtom reactively", () => {
    const store = createPanelStore(TEST_PANELS, { useDefaultLayout: true });
    expect(store.get(panelsInZoneAtom("top-left"))).toEqual(["info"]);

    const { result } = renderPanelEnabled(store);
    act(() => result.current.setEnabled("info", false));

    expect(store.get(panelsInZoneAtom("top-left"))).toEqual([]);
  });

  it("is a no-op when called for builtin panels", () => {
    const builtinPanels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, isBuiltin: true } : p,
    );
    const store = createPanelStore(builtinPanels, { useDefaultLayout: true });

    const { result } = renderPanelEnabled(store, builtinPanels);
    act(() => result.current.setEnabled("info", false));

    expect(store.get(panelsInZoneAtom("top-left"))).toEqual(["info"]);
  });
});

const Stub = (): null => {
  usePanelKeyboardShortcuts();
  return null;
};

const mountDispatch = (
  store: ReturnType<typeof createStore>,
  panels: ReadonlyArray<PanelDefinition>,
): {
  unmount: () => void;
  zones: Record<string, HTMLElement>;
} => {
  const zones: Record<string, HTMLElement> = {};
  for (const zone of ["top-left", "bottom-left", "bottom", "top-right", "bottom-right"] as const) {
    const el = document.createElement("div");
    el.setAttribute("data-zone-id", zone);
    el.tabIndex = -1;
    document.body.appendChild(el);
    zones[zone] = el;
  }
  const { unmount } = render(
    <Provider store={store}>
      <PanelRegistryProvider panels={panels}>
        <Stub />
      </PanelRegistryProvider>
    </Provider>,
  );
  return {
    unmount: (): void => {
      unmount();
      for (const el of Object.values(zones)) el.remove();
    },
    zones,
  };
};

const isMacOS = (): boolean =>
  (typeof window !== "undefined" && window.sculptor?.platform === "darwin") || navigator.platform.startsWith("Mac");

const fireMetaE = (): void => {
  const isMac = isMacOS();
  fireEvent.keyDown(window, {
    key: "e",
    metaKey: isMac,
    ctrlKey: !isMac,
  });
};

describe("usePanelKeyboardShortcuts focus-then-toggle dispatch", () => {
  it("press 1 on a hidden panel shows + activates it", () => {
    const panels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Meta+e" } : p,
    );
    const store = createPanelStore(panels, { useDefaultLayout: true });
    store.set(zoneVisibilityAtom, (prev) => ({ ...prev, "top-left": false }));

    const { unmount } = mountDispatch(store, panels);
    act(() => fireMetaE());

    expect(store.get(zoneVisibilityAtom)["top-left"]).toBe(true);
    expect(store.get(activePanelPerZoneAtom)["top-left"]).toBe("info");
    unmount();
  });

  it("press on a visible+focused panel hides the zone", () => {
    const panels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Meta+e" } : p,
    );
    const store = createPanelStore(panels, { useDefaultLayout: true });

    const { unmount, zones } = mountDispatch(store, panels);
    zones["top-left"].focus();
    expect(document.activeElement).toBe(zones["top-left"]);

    act(() => fireMetaE());

    expect(store.get(zoneVisibilityAtom)["top-left"]).toBe(false);
    unmount();
  });

  it("press on a visible-but-not-focused panel does not hide the zone", () => {
    const panels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Meta+e" } : p,
    );
    const store = createPanelStore(panels, { useDefaultLayout: true });

    const { unmount } = mountDispatch(store, panels);
    // Body has focus by default — the panel is visible but not focused.
    expect(document.activeElement).toBe(document.body);

    act(() => fireMetaE());

    expect(store.get(zoneVisibilityAtom)["top-left"]).toBe(true);
    unmount();
  });

  it("press on a panel that is not the active tab makes it active", () => {
    const panels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "cost" ? { ...p, defaultShortcut: "Meta+e", defaultZone: "top-left" } : p,
    );
    const store = createPanelStore(panels, { useDefaultLayout: true });
    // Make both info and cost share top-left, with info active.
    store.set(activePanelPerZoneAtom, (prev) => ({ ...prev, "top-left": "info" }));

    const { unmount } = mountDispatch(store, panels);
    act(() => fireMetaE());

    expect(store.get(activePanelPerZoneAtom)["top-left"]).toBe("cost");
    expect(store.get(zoneVisibilityAtom)["top-left"]).toBe(true);
    unmount();
  });

  it("disabled panels do not fire", () => {
    const panels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Meta+e" } : p,
    );
    const store = createPanelStore(panels, { useDefaultLayout: true });
    store.set(panelEnabledAtom, { info: false });

    const { unmount, zones } = mountDispatch(store, panels);
    zones["top-left"].focus();

    act(() => fireMetaE());

    // panelShortcutsAtom omits disabled panels, so no toggle fired.
    expect(store.get(zoneVisibilityAtom)["top-left"]).toBe(true);
    unmount();
  });

  it("calls panel.getFocusTarget() when present", () => {
    const customTarget = document.createElement("button");
    document.body.appendChild(customTarget);
    const focusSpy = vi.spyOn(customTarget, "focus");

    const panels: ReadonlyArray<PanelDefinition> = TEST_PANELS.map((p) =>
      p.id === "info" ? { ...p, defaultShortcut: "Meta+e", getFocusTarget: () => customTarget } : p,
    );
    const store = createPanelStore(panels, { useDefaultLayout: true });
    store.set(zoneVisibilityAtom, (prev) => ({ ...prev, "top-left": false }));

    const { unmount } = mountDispatch(store, panels);
    act(() => fireMetaE());

    expect(focusSpy).toHaveBeenCalled();

    customTarget.remove();
    unmount();
  });
});
