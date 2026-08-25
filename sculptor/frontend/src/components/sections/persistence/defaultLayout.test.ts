import { describe, expect, it } from "vitest";

import { buildDefaultWorkspaceLayout } from "./defaultLayout.ts";
import type { WorkspaceLayoutState } from "./types.ts";
import { DEFAULT_SECTION_SIZES } from "./types.ts";

// Pins the full arrangement produced by the pure default-layout builder, including
// the dynamic agent/terminal placements. Layout capture strips those instance-bound
// ids before the System Default tests see them, so the dynamic half of the output is
// only asserted here.

const AGENT_PANEL_ID = "agent:task-1";
const TERMINAL_PANEL_ID = "terminal:ws-1:1";

function buildDefault(): WorkspaceLayoutState {
  return buildDefaultWorkspaceLayout({ agentPanelId: AGENT_PANEL_ID, terminalPanelId: TERMINAL_PANEL_ID });
}

describe("buildDefaultWorkspaceLayout", () => {
  it("seeds the agent in center, the terminal in bottom, and the explorer panels in left", () => {
    expect(buildDefault().placement).toEqual({
      [AGENT_PANEL_ID]: "center",
      files: "left",
      changes: "left",
      commits: "left",
      [TERMINAL_PANEL_ID]: "bottom",
    });
  });

  it("orders each section's tabs with the dynamic ids in their sections", () => {
    expect(buildDefault().order).toEqual({
      center: [AGENT_PANEL_ID],
      left: ["files", "changes", "commits"],
      bottom: [TERMINAL_PANEL_ID],
    });
  });

  it("makes the agent, files, and terminal the active tab of their sections", () => {
    expect(buildDefault().activePanel).toEqual({
      center: AGENT_PANEL_ID,
      left: "files",
      bottom: TERMINAL_PANEL_ID,
    });
  });

  it("starts left expanded with right/bottom collapsed and center omitted", () => {
    const { expanded } = buildDefault();

    expect(expanded).toEqual({ left: true, right: false, bottom: false });
    // center carries no flag — it is always expanded, so the builder never keys it.
    expect("center" in expanded).toBe(false);
  });

  it("defaults to no splits, the default section sizes, and a center-focused sub-section", () => {
    const layout = buildDefault();

    expect(layout.splits).toEqual({});
    expect(layout.sectionSizes).toEqual(DEFAULT_SECTION_SIZES);
    expect(layout.activeSubSection).toBe("center");
  });

  it("threads the provided panel ids through to center and bottom without swapping them", () => {
    const layout = buildDefaultWorkspaceLayout({
      agentPanelId: "agent:other-task",
      terminalPanelId: "terminal:ws-9:3",
    });

    expect(layout.placement["agent:other-task"]).toBe("center");
    expect(layout.placement["terminal:ws-9:3"]).toBe("bottom");
    expect(layout.order.center).toEqual(["agent:other-task"]);
    expect(layout.order.bottom).toEqual(["terminal:ws-9:3"]);
    expect(layout.activePanel.center).toBe("agent:other-task");
    expect(layout.activePanel.bottom).toBe("terminal:ws-9:3");
  });

  it("builds fresh objects per call, sharing only the default-sizes constant", () => {
    const first = buildDefault();
    const second = buildDefault();

    expect(first).not.toBe(second);
    expect(first.placement).not.toBe(second.placement);
    expect(first.order).not.toBe(second.order);
    expect(first.order.left).not.toBe(second.order.left);
    expect(first.activePanel).not.toBe(second.activePanel);
    expect(first.expanded).not.toBe(second.expanded);
    expect(first.splits).not.toBe(second.splits);

    // sectionSizes is the one field returned by reference: every call hands back the
    // shared DEFAULT_SECTION_SIZES constant, so callers must treat the sizes as read-only.
    expect(first.sectionSizes).toBe(DEFAULT_SECTION_SIZES);
    expect(second.sectionSizes).toBe(DEFAULT_SECTION_SIZES);
  });
});
