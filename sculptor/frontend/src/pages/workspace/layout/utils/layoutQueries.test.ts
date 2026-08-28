import { describe, expect, it } from "vitest";

import type { WorkspaceLayoutState } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/pages/workspace/layout/persistence/snapshot.ts";
import type { PanelDefinition } from "~/pages/workspace/layout/registry/panelRegistry.ts";
import { buildStaticPanelDefinitions } from "~/pages/workspace/layout/registry/panelRegistry.ts";

import {
  isSectionExpanded,
  listAvailableLocations,
  listAvailableStaticPanels,
  listSubSections,
  openPanelsInSubSection,
} from "./layoutQueries.ts";

const layoutWith = (overrides: Partial<WorkspaceLayoutState>): WorkspaceLayoutState => {
  return { ...EMPTY_WORKSPACE_LAYOUT, ...overrides };
};

describe("isSectionExpanded", () => {
  it("treats center as always expanded", () => {
    expect(isSectionExpanded(EMPTY_WORKSPACE_LAYOUT, "center")).toBe(true);
    // Even an explicit collapsed flag cannot collapse center.
    expect(isSectionExpanded(layoutWith({ expanded: { center: false } }), "center")).toBe(true);
  });

  it("treats other sections as collapsed unless flagged expanded", () => {
    expect(isSectionExpanded(EMPTY_WORKSPACE_LAYOUT, "left")).toBe(false);
    expect(isSectionExpanded(layoutWith({ expanded: { left: true } }), "left")).toBe(true);
    expect(isSectionExpanded(layoutWith({ expanded: { left: false } }), "left")).toBe(false);
  });
});

describe("openPanelsInSubSection", () => {
  it("returns the sub-section's placed panels in tab order", () => {
    const layout = layoutWith({
      placement: { files: "left", changes: "left", commits: "right" },
      order: { left: ["changes", "files"], right: ["commits"] },
    });
    expect(openPanelsInSubSection(layout, "left")).toEqual(["changes", "files"]);
    expect(openPanelsInSubSection(layout, "right")).toEqual(["commits"]);
    expect(openPanelsInSubSection(layout, "bottom")).toEqual([]);
  });

  it("appends placed-but-unordered panels so no open panel is dropped", () => {
    const layout = layoutWith({
      placement: { files: "left", changes: "left" },
      order: { left: ["files"] },
    });
    expect(openPanelsInSubSection(layout, "left")).toEqual(["files", "changes"]);
  });

  it("ignores order entries whose panel is not placed in the sub-section", () => {
    const layout = layoutWith({
      placement: { files: "left" },
      // "changes" is closed (no placement) but still lingers in the order list.
      order: { left: ["changes", "files"] },
    });
    expect(openPanelsInSubSection(layout, "left")).toEqual(["files"]);
  });
});

describe("listSubSections", () => {
  it("steps through expanded sections only when collapsed ones are excluded", () => {
    const layout = layoutWith({ expanded: { left: true } });
    expect(listSubSections(layout, { includeCollapsed: false })).toEqual(["left", "center"]);
  });

  it("includes a split section's secondary half after its primary", () => {
    const layout = layoutWith({
      expanded: { left: true },
      splits: { left: { axis: "horizontal", ratio: 0.5 } },
    });
    expect(listSubSections(layout, { includeCollapsed: false })).toEqual(["left", "left:secondary", "center"]);
  });

  it("offers a collapsed section's primary — but not its split half — when collapsed ones are included", () => {
    // The left section is split but collapsed: its secondary is hidden until the
    // section is expanded again.
    const layout = layoutWith({ splits: { left: { axis: "horizontal", ratio: 0.5 } } });
    expect(listSubSections(layout, { includeCollapsed: true })).toEqual(["left", "center", "right", "bottom"]);
    expect(listSubSections(layout, { includeCollapsed: false })).toEqual(["center"]);
  });
});

describe("listAvailableLocations", () => {
  it("offers every section, including collapsed ones (adding a panel expands them)", () => {
    // Only 'left' is expanded; right/bottom are collapsed. Center is always available.
    const layout = layoutWith({ expanded: { left: true } });
    const subSections = listAvailableLocations(layout).map((location) => location.subSection);
    expect(subSections).toEqual(["left", "center", "right", "bottom"]);
  });

  it("labels a split section's halves as (primary)/(secondary) and unsplit sections plainly", () => {
    const layout = layoutWith({
      expanded: { left: true },
      splits: { left: { axis: "horizontal", ratio: 0.5 } },
    });
    expect(listAvailableLocations(layout)).toEqual([
      { subSection: "left", label: "Left (primary)" },
      { subSection: "left:secondary", label: "Left (secondary)" },
      { subSection: "center", label: "Center" },
      { subSection: "right", label: "Right" },
      { subSection: "bottom", label: "Bottom" },
    ]);
  });
});

describe("listAvailableStaticPanels", () => {
  const agentDefinition: PanelDefinition = {
    ...buildStaticPanelDefinitions()[0],
    id: "agent:t1",
    displayName: "Agent 1",
    kind: "agent",
  };

  it("offers only static panels that are not currently open", () => {
    const registry = [...buildStaticPanelDefinitions(), agentDefinition];
    const available = listAvailableStaticPanels(registry, { files: "left", "agent:t1": "center" });
    const ids = available.map((panel) => panel.id);
    // The open static panel is excluded; the closed static panels remain.
    expect(ids).not.toContain("files");
    expect(ids).toContain("changes");
    // The multi-instance agent panel is never in the re-add list, open or not.
    expect(ids).not.toContain("agent:t1");
  });

  it("offers every static panel when none are open", () => {
    const staticDefinitions = buildStaticPanelDefinitions();
    const available = listAvailableStaticPanels(staticDefinitions, {});
    expect(available.map((panel) => panel.id)).toEqual(staticDefinitions.map((definition) => definition.id));
  });
});
