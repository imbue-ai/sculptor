import { render } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { Circle } from "lucide-react";
import type { ReactElement } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  activePanelPerZoneAtom,
  panelRegistryAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import { PanelRegistryProvider } from "~/components/panels/PanelRegistryProvider";
import type { DefaultPanelLayout, PanelDefinition } from "~/components/panels/types.ts";

const INFO_PANEL: PanelDefinition = {
  id: "info",
  displayName: "Info",
  description: "Test info panel",
  icon: Circle,
  defaultZone: "top-left",
  defaultShortcut: "",
  component: () => createElement("div"),
};

const TERMINAL_PANEL: PanelDefinition = {
  id: "terminal",
  displayName: "Terminal",
  description: "Test terminal panel",
  icon: Circle,
  defaultZone: "bottom",
  defaultShortcut: "",
  component: () => createElement("div"),
};

const CHANGES_PANEL: PanelDefinition = {
  id: "changes",
  displayName: "Changes",
  description: "Test changes panel",
  icon: Circle,
  defaultZone: "top-right",
  defaultShortcut: "",
  component: () => createElement("div"),
};

const NOTES_PANEL: PanelDefinition = {
  id: "notes",
  displayName: "Notes",
  description: "Test notes panel",
  icon: Circle,
  defaultZone: "bottom-right",
  defaultShortcut: "",
  component: () => createElement("div"),
};

const TEST_PANELS: ReadonlyArray<PanelDefinition> = [INFO_PANEL, TERMINAL_PANEL, CHANGES_PANEL];

const EXTENDED_PANELS: ReadonlyArray<PanelDefinition> = [...TEST_PANELS, NOTES_PANEL];

const TEST_DEFAULT_LAYOUT: DefaultPanelLayout = {
  zoneAssignments: {
    info: "top-left",
    terminal: "bottom",
    changes: "top-right",
  },
  activePanelPerZone: {
    "top-left": "info",
    bottom: "terminal",
    "top-right": "changes",
  },
  zoneVisibility: {
    "top-left": true,
    bottom: true,
    "top-right": true,
  },
  zoneOrder: {
    "top-left": ["info"],
    bottom: ["terminal"],
    "top-right": ["changes"],
  },
};

type RenderProviderArgs = {
  store: ReturnType<typeof createStore>;
  panels: ReadonlyArray<PanelDefinition>;
  defaultLayout?: DefaultPanelLayout;
};

const buildTree = ({ store, panels, defaultLayout }: RenderProviderArgs): ReactElement => (
  <Provider store={store}>
    <PanelRegistryProvider panels={panels} defaultLayout={defaultLayout}>
      <div data-testid="child" />
    </PanelRegistryProvider>
  </Provider>
);

const renderProvider = (
  args: RenderProviderArgs,
): {
  rerender: (next: RenderProviderArgs) => void;
  unmount: () => void;
} => {
  const result = render(buildTree(args));
  return {
    rerender: (next: RenderProviderArgs): void => result.rerender(buildTree(next)),
    unmount: (): void => result.unmount(),
  };
};

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe("PanelRegistryProvider — bootstrap", () => {
  it("applies defaultLayout on first mount when no persisted layout exists", () => {
    const store = createStore();
    renderProvider({ store, panels: TEST_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(zoneAssignmentsAtom)).toEqual(TEST_DEFAULT_LAYOUT.zoneAssignments);
    expect(store.get(activePanelPerZoneAtom)).toEqual(TEST_DEFAULT_LAYOUT.activePanelPerZone);
    expect(store.get(zoneVisibilityAtom)).toEqual(TEST_DEFAULT_LAYOUT.zoneVisibility);
    expect(store.get(zoneOrderAtom)).toEqual(TEST_DEFAULT_LAYOUT.zoneOrder);
  });

  it("leaves layout atoms empty when no defaultLayout is provided", () => {
    const store = createStore();
    renderProvider({ store, panels: TEST_PANELS });

    expect(store.get(zoneAssignmentsAtom)).toEqual({});
    expect(store.get(activePanelPerZoneAtom)).toEqual({});
    expect(store.get(zoneVisibilityAtom)).toEqual({});
    expect(store.get(zoneOrderAtom)).toEqual({});
  });

  it("does not re-apply defaultLayout when zoneAssignments is already populated", () => {
    const store = createStore();
    // Seed with an existing user-configured assignment that differs from the
    // defaultLayout (info is placed in "bottom" instead of "top-left").
    store.set(zoneAssignmentsAtom, { info: "bottom", terminal: "bottom", changes: "top-right" });

    renderProvider({ store, panels: TEST_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    // The bootstrap effect must not overwrite the existing assignments with
    // defaultLayout.zoneAssignments. The user-configured zone for "info" stays.
    expect(store.get(zoneAssignmentsAtom).info).toBe("bottom");
    // activePanelPerZone and zoneVisibility are bootstrap-only atoms — they
    // must remain untouched when zoneAssignments is already populated.
    expect(store.get(activePanelPerZoneAtom)).toEqual({});
    expect(store.get(zoneVisibilityAtom)).toEqual({});
  });
});

describe("PanelRegistryProvider — registry sync", () => {
  it("hydrates panelRegistryAtom with initial panels on mount", () => {
    const store = createStore();
    renderProvider({ store, panels: TEST_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(panelRegistryAtom)).toEqual(TEST_PANELS);
  });

  it("updates panelRegistryAtom when the panels prop changes", () => {
    const store = createStore();
    const { rerender } = renderProvider({
      store,
      panels: TEST_PANELS,
      defaultLayout: TEST_DEFAULT_LAYOUT,
    });

    expect(store.get(panelRegistryAtom)).toEqual(TEST_PANELS);

    rerender({ store, panels: EXTENDED_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(panelRegistryAtom)).toEqual(EXTENDED_PANELS);
  });
});

describe("PanelRegistryProvider — reconciliation (adding panels)", () => {
  it("adds a newly-registered panel to zoneAssignments at its defaultZone", () => {
    const store = createStore();
    const { rerender } = renderProvider({
      store,
      panels: TEST_PANELS,
      defaultLayout: TEST_DEFAULT_LAYOUT,
    });

    rerender({ store, panels: EXTENDED_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBe("bottom-right");
  });

  it("appends a newly-registered panel to zoneOrder for its zone", () => {
    const store = createStore();
    const { rerender } = renderProvider({
      store,
      panels: TEST_PANELS,
      defaultLayout: TEST_DEFAULT_LAYOUT,
    });

    rerender({ store, panels: EXTENDED_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    const bottomRightOrder = store.get(zoneOrderAtom)["bottom-right"];
    expect(bottomRightOrder).toBeDefined();
    expect(bottomRightOrder!).toContain(NOTES_PANEL.id);
    expect(bottomRightOrder![bottomRightOrder!.length - 1]).toBe(NOTES_PANEL.id);
  });

  it("creates a zoneOrder entry for a zone that had no prior entry in defaultLayout", () => {
    // The default layout does not include "bottom-right" in zoneOrder. Adding
    // a panel whose defaultZone is bottom-right must create the entry.
    const store = createStore();
    const { rerender } = renderProvider({
      store,
      panels: TEST_PANELS,
      defaultLayout: TEST_DEFAULT_LAYOUT,
    });

    expect(store.get(zoneOrderAtom)["bottom-right"]).toBeUndefined();

    rerender({ store, panels: EXTENDED_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(zoneOrderAtom)["bottom-right"]).toEqual([NOTES_PANEL.id]);
    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBe("bottom-right");
  });
});

describe("PanelRegistryProvider — reconciliation (removing panels)", () => {
  it("removes stale panels from zoneAssignments when they disappear from props", () => {
    const store = createStore();
    const extendedDefaultLayout: DefaultPanelLayout = {
      zoneAssignments: { ...TEST_DEFAULT_LAYOUT.zoneAssignments, notes: "bottom-right" },
      activePanelPerZone: { ...TEST_DEFAULT_LAYOUT.activePanelPerZone, "bottom-right": "notes" },
      zoneVisibility: { ...TEST_DEFAULT_LAYOUT.zoneVisibility, "bottom-right": true },
      zoneOrder: { ...TEST_DEFAULT_LAYOUT.zoneOrder, "bottom-right": ["notes"] },
    };

    const { rerender } = renderProvider({
      store,
      panels: EXTENDED_PANELS,
      defaultLayout: extendedDefaultLayout,
    });

    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBe("bottom-right");

    rerender({ store, panels: TEST_PANELS, defaultLayout: extendedDefaultLayout });

    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBeUndefined();
  });

  it("removes stale panels from zoneOrder for every zone", () => {
    const store = createStore();
    const extendedDefaultLayout: DefaultPanelLayout = {
      zoneAssignments: { ...TEST_DEFAULT_LAYOUT.zoneAssignments, notes: "bottom-right" },
      activePanelPerZone: { ...TEST_DEFAULT_LAYOUT.activePanelPerZone, "bottom-right": "notes" },
      zoneVisibility: { ...TEST_DEFAULT_LAYOUT.zoneVisibility, "bottom-right": true },
      zoneOrder: { ...TEST_DEFAULT_LAYOUT.zoneOrder, "bottom-right": ["notes"] },
    };

    const { rerender } = renderProvider({
      store,
      panels: EXTENDED_PANELS,
      defaultLayout: extendedDefaultLayout,
    });

    rerender({ store, panels: TEST_PANELS, defaultLayout: extendedDefaultLayout });

    const order = store.get(zoneOrderAtom);
    for (const zoneId of Object.keys(order)) {
      const zoneOrder = order[zoneId as keyof typeof order];
      if (zoneOrder) {
        expect(zoneOrder).not.toContain(NOTES_PANEL.id);
      }
    }
  });

  it("falls back to the next remaining panel in the zone when the active panel is removed", () => {
    const store = createStore();
    // Seed a zone with two panels, panelA active.
    const panelA: PanelDefinition = { ...INFO_PANEL, id: "panelA", defaultZone: "top-left" };
    const panelB: PanelDefinition = { ...INFO_PANEL, id: "panelB", defaultZone: "top-left" };

    const seededLayout: DefaultPanelLayout = {
      zoneAssignments: { panelA: "top-left", panelB: "top-left" },
      activePanelPerZone: { "top-left": "panelA" },
      zoneVisibility: { "top-left": true },
      zoneOrder: { "top-left": ["panelA", "panelB"] },
    };

    const { rerender } = renderProvider({
      store,
      panels: [panelA, panelB],
      defaultLayout: seededLayout,
    });

    expect(store.get(activePanelPerZoneAtom)["top-left"]).toBe("panelA");

    // Remove panelA — active should fall back to panelB.
    rerender({ store, panels: [panelB], defaultLayout: seededLayout });
    expect(store.get(activePanelPerZoneAtom)["top-left"]).toBe("panelB");

    // Remove panelB — zone becomes empty, active becomes undefined.
    rerender({ store, panels: [], defaultLayout: seededLayout });
    expect(store.get(activePanelPerZoneAtom)["top-left"]).toBeUndefined();
  });
});

describe("PanelRegistryProvider — idempotency", () => {
  it("rerendering with the same panels reference does not change state", () => {
    const store = createStore();
    const { rerender } = renderProvider({
      store,
      panels: TEST_PANELS,
      defaultLayout: TEST_DEFAULT_LAYOUT,
    });

    const assignmentsBefore = store.get(zoneAssignmentsAtom);
    const orderBefore = store.get(zoneOrderAtom);
    const activeBefore = store.get(activePanelPerZoneAtom);
    const visibilityBefore = store.get(zoneVisibilityAtom);

    rerender({ store, panels: TEST_PANELS, defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(zoneAssignmentsAtom)).toEqual(assignmentsBefore);
    expect(store.get(zoneOrderAtom)).toEqual(orderBefore);
    expect(store.get(activePanelPerZoneAtom)).toEqual(activeBefore);
    expect(store.get(zoneVisibilityAtom)).toEqual(visibilityBefore);
  });

  it("rerendering with a fresh array of the same contents does not change state", () => {
    const store = createStore();
    const { rerender } = renderProvider({
      store,
      panels: TEST_PANELS,
      defaultLayout: TEST_DEFAULT_LAYOUT,
    });

    const assignmentsBefore = store.get(zoneAssignmentsAtom);
    const orderBefore = store.get(zoneOrderAtom);

    rerender({ store, panels: [...TEST_PANELS], defaultLayout: TEST_DEFAULT_LAYOUT });

    expect(store.get(zoneAssignmentsAtom)).toEqual(assignmentsBefore);
    expect(store.get(zoneOrderAtom)).toEqual(orderBefore);
  });

  it("toggling a panel off then on again yields the original assignment", () => {
    const store = createStore();
    const extendedDefaultLayout: DefaultPanelLayout = {
      zoneAssignments: { ...TEST_DEFAULT_LAYOUT.zoneAssignments, notes: "bottom-right" },
      activePanelPerZone: { ...TEST_DEFAULT_LAYOUT.activePanelPerZone, "bottom-right": "notes" },
      zoneVisibility: { ...TEST_DEFAULT_LAYOUT.zoneVisibility, "bottom-right": true },
      zoneOrder: { ...TEST_DEFAULT_LAYOUT.zoneOrder, "bottom-right": ["notes"] },
    };

    const { rerender } = renderProvider({
      store,
      panels: EXTENDED_PANELS,
      defaultLayout: extendedDefaultLayout,
    });

    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBe("bottom-right");

    rerender({ store, panels: TEST_PANELS, defaultLayout: extendedDefaultLayout });
    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBeUndefined();

    rerender({ store, panels: EXTENDED_PANELS, defaultLayout: extendedDefaultLayout });
    expect(store.get(zoneAssignmentsAtom)[NOTES_PANEL.id]).toBe("bottom-right");
    expect(store.get(zoneOrderAtom)["bottom-right"]).toContain(NOTES_PANEL.id);
  });
});
