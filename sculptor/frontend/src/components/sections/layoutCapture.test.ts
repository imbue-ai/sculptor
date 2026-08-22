import { describe, expect, it } from "vitest";

import { captureLayout } from "./layoutCapture.ts";
import type { WorkspaceLayoutState } from "./persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "./persistence/types.ts";

function layoutWith(overrides: Partial<WorkspaceLayoutState>): WorkspaceLayoutState {
  return { ...EMPTY_WORKSPACE_LAYOUT, ...overrides };
}

describe("captureLayout", () => {
  it("keeps static panels and strips agent/terminal panels from placement/order/activePanel", () => {
    const layout = layoutWith({
      placement: {
        files: "left",
        changes: "left",
        "agent:123": "center",
        "terminal:ws-1:1": "bottom",
      },
      order: {
        left: ["files", "changes"],
        center: ["agent:123"],
        bottom: ["terminal:ws-1:1"],
      },
      activePanel: { left: "files", center: "agent:123", bottom: "terminal:ws-1:1" },
      activeSubSection: "center",
    });

    const captured = captureLayout(layout, null);

    expect(captured.placement).toEqual({ files: "left", changes: "left" });
    // Sub-sections that held only dynamic panels are pruned entirely.
    expect(captured.order).toEqual({ left: ["files", "changes"] });
    // The active tab is kept only where it names a static panel.
    expect(captured.activePanel).toEqual({ left: "files" });
  });

  it("captures geometry fields verbatim and takes maximize from the argument", () => {
    const layout = layoutWith({
      expanded: { left: true, right: false, bottom: true },
      splits: { bottom: { axis: "vertical", ratio: 0.4 } },
      sectionSizes: { left: 18, right: 22, bottom: 33 },
      activeSubSection: "bottom:secondary",
    });

    const captured = captureLayout(layout, "left");

    expect(captured.expanded).toEqual({ left: true, right: false, bottom: true });
    expect(captured.splits).toEqual({ bottom: { axis: "vertical", ratio: 0.4 } });
    expect(captured.sectionSizes).toEqual({ left: 18, right: 22, bottom: 33 });
    expect(captured.activeSubSection).toBe("bottom:secondary");
    expect(captured.maximizedSection).toBe("left");
  });

  it("does not alias the source layout's nested objects", () => {
    const layout = layoutWith({
      expanded: { left: true },
      splits: {},
      sectionSizes: { left: 20, right: 20, bottom: 30 },
    });
    const captured = captureLayout(layout, null);
    captured.expanded.left = false;
    captured.sectionSizes.left = 99;
    expect(layout.expanded.left).toBe(true);
    expect(layout.sectionSizes.left).toBe(20);
  });
});
