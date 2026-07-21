import { describe, expect, it } from "vitest";

import { applyCapturedLayout, computeTidyClosure, seedWorkspaceFromDefault } from "./layoutApply.ts";
import type { CapturedLayout, SavedLayout, WorkspaceLayoutState } from "./persistence/types.ts";
import { DEFAULT_SECTION_SIZES, EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "./persistence/types.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID } from "./systemDefaultLayout.ts";

function layoutWith(overrides: Partial<WorkspaceLayoutState>): WorkspaceLayoutState {
  return { ...EMPTY_WORKSPACE_LAYOUT, ...overrides };
}

function captured(overrides: Partial<CapturedLayout>): CapturedLayout {
  return {
    placement: {},
    order: {},
    activePanel: {},
    expanded: {},
    splits: {},
    sectionSizes: DEFAULT_SECTION_SIZES,
    maximizedSection: null,
    activeSubSection: null,
    ...overrides,
  };
}

describe("applyCapturedLayout — additive apply (Rule 2)", () => {
  it("never closes a panel: agents, terminals and undeclared statics all survive", () => {
    const current = layoutWith({
      placement: { "agent:1": "center", browser: "right", "terminal:ws:1": "bottom" },
      order: { center: ["agent:1"], right: ["browser"], bottom: ["terminal:ws:1"] },
      expanded: { right: true, bottom: true },
      activeSubSection: "center",
    });
    // A layout that declares only Files in the left, and collapses right + bottom.
    const { layout } = applyCapturedLayout(
      current,
      captured({ placement: { files: "left" }, order: { left: ["files"] }, expanded: { left: true } }),
    );

    expect(layout.placement["agent:1"]).toBe("center");
    expect(layout.placement.browser).toBe("right");
    expect(layout.placement["terminal:ws:1"]).toBe("bottom");
    // ...and the declared static is opened where the layout puts it.
    expect(layout.placement.files).toBe("left");
  });

  it("moves a declared static to its captured section and cleans the old one", () => {
    const current = layoutWith({
      placement: { changes: "left" },
      order: { left: ["changes"] },
      expanded: { left: true },
    });
    const { layout } = applyCapturedLayout(
      current,
      captured({ placement: { changes: "right" }, order: { right: ["changes"] }, expanded: { right: true } }),
    );

    expect(layout.placement.changes).toBe("right");
    expect(layout.order.right).toEqual(["changes"]);
    expect(layout.order.left ?? []).toEqual([]);
  });

  it("orders declared statics first, then the section's residual panels in place", () => {
    const current = layoutWith({
      placement: { "agent:1": "center", files: "center" },
      order: { center: ["agent:1", "files"] },
      activeSubSection: "center",
    });
    const { layout } = applyCapturedLayout(
      current,
      captured({ placement: { notes: "center" }, order: { center: ["notes"] } }),
    );

    expect(layout.order.center).toEqual(["notes", "agent:1", "files"]);
  });

  it("collapses a section (geometry) without closing its residual panel", () => {
    const current = layoutWith({
      placement: { browser: "right" },
      order: { right: ["browser"] },
      expanded: { right: true },
    });
    const { layout } = applyCapturedLayout(current, captured({ expanded: {} }));

    expect(layout.placement.browser).toBe("right");
    expect(layout.expanded.right ?? false).toBe(false);
  });

  it("relocates a panel stranded in a split half the layout does not split", () => {
    const current = layoutWith({
      placement: { files: "bottom", "terminal:x:1": "bottom:secondary" },
      order: { bottom: ["files"], "bottom:secondary": ["terminal:x:1"] },
      splits: { bottom: { axis: "vertical", ratio: 0.5 } },
      expanded: { bottom: true },
    });
    const { layout } = applyCapturedLayout(current, captured({ expanded: { bottom: true }, splits: {} }));

    expect(layout.splits.bottom).toBeUndefined();
    // The terminal moves back to the primary rather than lingering in a phantom half.
    expect(layout.placement["terminal:x:1"]).toBe("bottom");
    expect(layout.order.bottom).toEqual(["files", "terminal:x:1"]);
  });

  it("restores the captured active tab when present and sets geometry verbatim", () => {
    const current = layoutWith({
      placement: { files: "left", changes: "left" },
      order: { left: ["files", "changes"] },
      activePanel: { left: "files" },
      expanded: { left: true },
    });
    const { layout } = applyCapturedLayout(
      current,
      captured({
        placement: { files: "left", changes: "left" },
        order: { left: ["changes", "files"] },
        activePanel: { left: "changes" },
        expanded: { left: true },
        splits: { left: { axis: "horizontal", ratio: 0.3 } },
        sectionSizes: { left: 18, right: 22, bottom: 33 },
      }),
    );

    expect(layout.order.left).toEqual(["changes", "files"]);
    expect(layout.activePanel.left).toBe("changes");
    expect(layout.splits.left).toEqual({ axis: "horizontal", ratio: 0.3 });
    expect(layout.sectionSizes).toEqual({ left: 18, right: 22, bottom: 33 });
  });
});

describe("applyCapturedLayout — focus + maximize guards", () => {
  it("drops a maximize whose section ends up collapsed and keeps a valid one", () => {
    const current = layoutWith({});
    expect(
      applyCapturedLayout(current, captured({ maximizedSection: "right", expanded: {} })).maximizedSection,
    ).toBeNull();
    expect(
      applyCapturedLayout(current, captured({ maximizedSection: "left", expanded: { left: true } })).maximizedSection,
    ).toBe("left");
    // Center is always expanded, so a center maximize always survives.
    expect(applyCapturedLayout(current, captured({ maximizedSection: "center" })).maximizedSection).toBe("center");
  });

  it("falls back to center when the captured active sub-section ends up collapsed", () => {
    const current = layoutWith({});
    expect(
      applyCapturedLayout(current, captured({ activeSubSection: "right", expanded: {} })).layout.activeSubSection,
    ).toBe("center");
    expect(
      applyCapturedLayout(current, captured({ activeSubSection: "left", expanded: { left: true } })).layout
        .activeSubSection,
    ).toBe("left");
  });
});

describe("seedWorkspaceFromDefault", () => {
  const base = layoutWith({
    placement: { "agent:1": "center", files: "left", "terminal:ws:1": "bottom" },
    order: { center: ["agent:1"], left: ["files"], bottom: ["terminal:ws:1"] },
    expanded: { left: true, right: false, bottom: false },
    activeSubSection: "center",
  });

  it("returns the plain base (just stamped) for System Default", () => {
    const seeded = seedWorkspaceFromDefault(base, SYSTEM_DEFAULT_LAYOUT);
    expect(seeded.appliedLayoutId).toBe(SYSTEM_DEFAULT_LAYOUT_ID);
    expect(seeded.placement).toEqual(base.placement);
    expect(seeded.expanded).toEqual(base.expanded);
  });

  it("applies a custom default's geometry over the seeded agent + terminal", () => {
    // A "Focused"-style default: no static panels, everything but center collapsed.
    const focused: SavedLayout = {
      id: "focused",
      name: "Focused",
      version: SAVED_LAYOUT_VERSION,
      captured: {
        placement: {},
        order: {},
        activePanel: {},
        expanded: {},
        splits: {},
        sectionSizes: DEFAULT_SECTION_SIZES,
        maximizedSection: null,
        activeSubSection: "center",
      },
    };
    const seeded = seedWorkspaceFromDefault(base, focused);

    expect(seeded.appliedLayoutId).toBe("focused");
    // The seeded agent, terminal and files are all still placed (never closed)...
    expect(seeded.placement["agent:1"]).toBe("center");
    expect(seeded.placement["terminal:ws:1"]).toBe("bottom");
    expect(seeded.placement.files).toBe("left");
    // ...but left is now collapsed to match the default's geometry.
    expect(seeded.expanded.left ?? false).toBe(false);
  });
});

describe("computeTidyClosure", () => {
  it("returns the open statics the layout does not declare, never agents/terminals", () => {
    const current = layoutWith({
      placement: { files: "left", browser: "right", notes: "right", "agent:1": "center", "terminal:x:1": "bottom" },
    });
    const closure = computeTidyClosure(current, captured({ placement: { files: "left" } }));

    expect(closure).toEqual([
      { panelId: "browser", subSection: "right" },
      { panelId: "notes", subSection: "right" },
    ]);
  });

  it("is empty when every open static is declared", () => {
    const current = layoutWith({ placement: { files: "left", "agent:1": "center" } });
    expect(computeTidyClosure(current, captured({ placement: { files: "left" } }))).toEqual([]);
  });
});
