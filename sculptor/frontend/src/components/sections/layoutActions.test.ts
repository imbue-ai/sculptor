import { createStore } from "jotai";
import { beforeEach, describe, expect, it } from "vitest";

import {
  applyLayoutAtom,
  deleteLayoutAtom,
  saveCurrentLayoutAtom,
  setDefaultLayoutAtom,
  tidyToLayoutAtom,
  updateLayoutAtom,
} from "./layoutActions.ts";
import type { SavedLayout, WorkspaceLayoutState } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import {
  appliedLayoutIdAtom,
  defaultLayoutIdAtom,
  layoutMruAtom,
  savedLayoutsAtom,
  tidyConfirmationSuppressedAtom,
} from "./savedLayoutAtoms.ts";
import { activeWorkspaceIdAtom, panelsInSubSectionAtom, workspaceLayoutAtom } from "./sectionAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID } from "./systemDefaultLayout.ts";
import { activeSectionRingNonceAtom, layoutTidyTargetAtom, maximizedSectionAtom } from "./transientAtoms.ts";

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

  it("hands off to the Tidy confirmation only when the layout opts into tidy-on-apply", () => {
    const plain = storeWith({ placement: { browser: "right" }, expanded: { right: true } });
    plain.set(applyLayoutAtom, makeLayout("plain", { tidyOnApply: false }));
    expect(plain.get(layoutTidyTargetAtom)).toBeNull();

    const tidy = storeWith({ placement: { browser: "right" }, expanded: { right: true } });
    const flagged = makeLayout("flagged", { tidyOnApply: true });
    tidy.set(applyLayoutAtom, flagged);
    expect(tidy.get(layoutTidyTargetAtom)).toBe(flagged);
  });

  it("tidies silently — no confirmation — when the global suppression is set", () => {
    const store = storeWith({ placement: { browser: "right" }, expanded: { right: true } });
    store.set(tidyConfirmationSuppressedAtom, true);
    // System Default declares Files/Changes/Commits, so Browser is undeclared and
    // would close. With the confirmation globally suppressed, apply closes it outright.
    store.set(applyLayoutAtom, makeLayout("silent", { captured: SYSTEM_DEFAULT_LAYOUT.captured, tidyOnApply: true }));

    expect(store.get(layoutTidyTargetAtom)).toBeNull();
    expect(store.get(workspaceLayoutAtom).placement.browser).toBeUndefined();
    expect(store.get(panelsInSubSectionAtom("left"))).toEqual(["files", "changes", "commits"]);
  });

  it("suppression is global — it silences a different tidy layout too", () => {
    const store = storeWith({ placement: { browser: "right" }, expanded: { right: true } });
    store.set(tidyConfirmationSuppressedAtom, true);
    // A second, unrelated tidy layout also skips the confirmation (the flag is not
    // keyed to any one layout).
    store.set(applyLayoutAtom, makeLayout("other", { captured: SYSTEM_DEFAULT_LAYOUT.captured, tidyOnApply: true }));
    expect(store.get(layoutTidyTargetAtom)).toBeNull();
    expect(store.get(workspaceLayoutAtom).placement.browser).toBeUndefined();
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

    const id = store.set(saveCurrentLayoutAtom, { name: "  My layout  ", setAsDefault: true, tidyOnApply: true });

    const saved = store.get(savedLayoutsAtom);
    expect(saved).toHaveLength(1);
    expect(saved[0].id).toBe(id);
    expect(saved[0].name).toBe("My layout");
    expect(saved[0].tidyOnApply).toBe(true);
    // The agent is dynamic — never captured.
    expect(saved[0].captured.placement).toEqual({ files: "left" });
    expect(store.get(appliedLayoutIdAtom)).toBe(id);
    expect(store.get(layoutMruAtom)[0]).toBe(id);
    expect(store.get(defaultLayoutIdAtom)).toBe(id);
  });

  it("does not set default when the flag is off", () => {
    const store = storeWith({ placement: { files: "left" } });
    store.set(saveCurrentLayoutAtom, { name: "Plain", setAsDefault: false, tidyOnApply: false });
    expect(store.get(defaultLayoutIdAtom)).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
  });
});

describe("updateLayoutAtom", () => {
  it("updates name + tidy without touching the captured arrangement", () => {
    const store = storeWith({ placement: { files: "left" } });
    const original = makeLayout("a", { name: "Old", tidyOnApply: false });
    store.set(savedLayoutsAtom, [original]);

    store.set(updateLayoutAtom, { id: "a", name: "  New name  ", setAsDefault: false, tidyOnApply: true });

    const updated = store.get(savedLayoutsAtom)[0];
    expect(updated.name).toBe("New name");
    expect(updated.tidyOnApply).toBe(true);
    expect(updated.captured).toBe(original.captured);
  });

  it("keeps the existing name when the edit clears it", () => {
    const store = storeWith({ placement: { files: "left" } });
    store.set(savedLayoutsAtom, [makeLayout("a", { name: "Keep" })]);
    store.set(updateLayoutAtom, { id: "a", name: "   ", setAsDefault: false, tidyOnApply: false });
    expect(store.get(savedLayoutsAtom)[0].name).toBe("Keep");
  });

  it("owns the default pointer for this layout only", () => {
    const store = storeWith({ placement: { files: "left" } });
    store.set(savedLayoutsAtom, [makeLayout("a"), makeLayout("b")]);

    // Turning the flag on points the default here...
    store.set(updateLayoutAtom, { id: "a", name: "a", setAsDefault: true, tidyOnApply: false });
    expect(store.get(defaultLayoutIdAtom)).toBe("a");

    // ...editing a DIFFERENT layout with the flag off never steals it...
    store.set(updateLayoutAtom, { id: "b", name: "b", setAsDefault: false, tidyOnApply: false });
    expect(store.get(defaultLayoutIdAtom)).toBe("a");

    // ...but turning it off on the current default reverts to System Default.
    store.set(updateLayoutAtom, { id: "a", name: "a", setAsDefault: false, tidyOnApply: false });
    expect(store.get(defaultLayoutIdAtom)).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
  });

  it("is a no-op for System Default", () => {
    const store = storeWith({ placement: { files: "left" } });
    store.set(updateLayoutAtom, { id: SYSTEM_DEFAULT_LAYOUT_ID, name: "Nope", setAsDefault: true, tidyOnApply: true });
    expect(store.get(savedLayoutsAtom)).toHaveLength(0);
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

describe("setDefaultLayoutAtom", () => {
  it("points the default at a layout", () => {
    const store = storeWith({});
    store.set(setDefaultLayoutAtom, "focused");
    expect(store.get(defaultLayoutIdAtom)).toBe("focused");
  });
});
