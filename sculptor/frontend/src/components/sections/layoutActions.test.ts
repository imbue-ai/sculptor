import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import {
  applyLayoutAtom,
  deleteLayoutAtom,
  renameLayoutAtom,
  saveCurrentLayoutAtom,
  setDefaultLayoutAtom,
  tidyToLayoutAtom,
} from "./layoutActions.ts";
import type { SavedLayout, WorkspaceLayoutState } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { appliedLayoutIdAtom, defaultLayoutIdAtom, layoutMruAtom, savedLayoutsAtom } from "./savedLayoutAtoms.ts";
import { activeWorkspaceIdAtom, panelsInSubSectionAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID } from "./systemDefaultLayout.ts";
import { activeSectionRingNonceAtom, maximizedSectionAtom } from "./transientAtoms.ts";

function storeWith(layout: Partial<WorkspaceLayoutState>, workspaceId = "ws-1"): ReturnType<typeof createStore> {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, workspaceId);
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
  return store;
}

function makeLayout(id: string, overrides: Partial<SavedLayout> = {}): SavedLayout {
  return { id, name: id, version: SAVED_LAYOUT_VERSION, captured: SYSTEM_DEFAULT_LAYOUT.captured, ...overrides };
}

beforeEach(() => {
  localStorage.clear();
});

describe("applyLayoutAtom", () => {
  it("applies additively, records the pointer, fronts the MRU and pulses the ring", () => {
    const store = storeWith({
      placement: { "agent:1": "center", browser: "right" },
      order: { center: ["agent:1"], right: ["browser"] },
      expanded: { right: true },
      activeSubSection: "center",
    });
    const nonceBefore = store.get(activeSectionRingNonceAtom);

    store.set(applyLayoutAtom, SYSTEM_DEFAULT_LAYOUT);

    // System Default opens Files/Changes/Commits in the left...
    expect(store.get(panelsInSubSectionAtom("left"))).toEqual(["files", "changes", "commits"]);
    // ...without closing the agent or the Browser (additive).
    expect(store.get(panelsInSubSectionAtom("center"))).toEqual(["agent:1"]);
    expect(store.get(workspaceLayoutAtom).placement.browser).toBe("right");

    expect(store.get(appliedLayoutIdAtom)).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
    expect(store.get(layoutMruAtom)[0]).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
    expect(store.get(activeSectionRingNonceAtom)).toBe(nonceBefore + 1);
  });

  it("sets maximize from the layout", () => {
    const store = storeWith({ expanded: { left: true } });
    store.set(
      applyLayoutAtom,
      makeLayout("max", { captured: { ...SYSTEM_DEFAULT_LAYOUT.captured, maximizedSection: "left" } }),
    );
    expect(store.get(maximizedSectionAtom)).toBe("left");
  });
});

describe("tidyToLayoutAtom", () => {
  it("closes the undeclared statics but never agents/terminals", () => {
    const store = storeWith({
      placement: { files: "left", browser: "right", "agent:1": "center", "terminal:ws-1:1": "bottom" },
      order: { left: ["files"], right: ["browser"], center: ["agent:1"], bottom: ["terminal:ws-1:1"] },
      expanded: { left: true, right: true, bottom: true },
    });
    // System Default declares Files/Changes/Commits — Browser is undeclared.
    store.set(tidyToLayoutAtom, SYSTEM_DEFAULT_LAYOUT);

    expect(store.get(workspaceLayoutAtom).placement.browser).toBeUndefined();
    expect(store.get(workspaceLayoutAtom).placement["agent:1"]).toBe("center");
    expect(store.get(workspaceLayoutAtom).placement["terminal:ws-1:1"]).toBe("bottom");
  });
});

describe("saveCurrentLayoutAtom", () => {
  it("captures the current arrangement (statics only), marks it applied, and can set default", () => {
    const store = storeWith({
      placement: { files: "left", "agent:1": "center" },
      order: { left: ["files"], center: ["agent:1"] },
      expanded: { left: true },
      activeSubSection: "center",
    });

    const id = store.set(saveCurrentLayoutAtom, { name: "  My layout  ", setAsDefault: true });

    const saved = store.get(savedLayoutsAtom);
    expect(saved).toHaveLength(1);
    expect(saved[0].id).toBe(id);
    expect(saved[0].name).toBe("My layout");
    // The agent is dynamic — never captured.
    expect(saved[0].captured.placement).toEqual({ files: "left" });
    expect(store.get(appliedLayoutIdAtom)).toBe(id);
    expect(store.get(layoutMruAtom)[0]).toBe(id);
    expect(store.get(defaultLayoutIdAtom)).toBe(id);
  });

  it("does not set default when the flag is off", () => {
    const store = storeWith({ placement: { files: "left" } });
    store.set(saveCurrentLayoutAtom, { name: "Plain", setAsDefault: false });
    expect(store.get(defaultLayoutIdAtom)).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
  });
});

describe("deleteLayoutAtom", () => {
  it("removes the layout, prunes MRU, and resets default + applied pointers to fall back", () => {
    const store = storeWith({});
    const layout = makeLayout("focused");
    store.set(savedLayoutsAtom, [layout]);
    store.set(defaultLayoutIdAtom, "focused");
    store.set(layoutMruAtom, ["focused", SYSTEM_DEFAULT_LAYOUT_ID]);
    store.set(appliedLayoutIdAtom, "focused");

    store.set(deleteLayoutAtom, "focused");

    expect(store.get(savedLayoutsAtom)).toEqual([]);
    expect(store.get(layoutMruAtom)).toEqual([SYSTEM_DEFAULT_LAYOUT_ID]);
    expect(store.get(defaultLayoutIdAtom)).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
    expect(store.get(appliedLayoutIdAtom)).toBeUndefined();
  });

  it("refuses to delete System Default", () => {
    const store = storeWith({});
    store.set(savedLayoutsAtom, [makeLayout("keep")]);
    store.set(deleteLayoutAtom, SYSTEM_DEFAULT_LAYOUT_ID);
    expect(store.get(savedLayoutsAtom)).toHaveLength(1);
  });
});

describe("setDefaultLayoutAtom + renameLayoutAtom", () => {
  it("points the default at a layout", () => {
    const store = storeWith({});
    store.set(setDefaultLayoutAtom, "focused");
    expect(store.get(defaultLayoutIdAtom)).toBe("focused");
  });

  it("renames a saved layout, but leaves System Default and empty names alone", () => {
    const store = storeWith({});
    store.set(savedLayoutsAtom, [makeLayout("focused", { name: "Focused" })]);

    store.set(renameLayoutAtom, { id: "focused", name: "  Deep work  " });
    expect(store.get(savedLayoutsAtom)[0].name).toBe("Deep work");

    store.set(renameLayoutAtom, { id: "focused", name: "   " });
    expect(store.get(savedLayoutsAtom)[0].name).toBe("Deep work");

    store.set(renameLayoutAtom, { id: SYSTEM_DEFAULT_LAYOUT_ID, name: "Nope" });
    expect(store.get(savedLayoutsAtom)).toHaveLength(1);
  });
});
