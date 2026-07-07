// The default workspace arrangement, seeded on a workspace's FIRST visit. It is
// built here as a pure function so it can be unit-tested and reused; the dynamic
// agent/terminal ids are resolved by the caller (the bootstrap) from the active
// task and the first-visit seeded terminal — never hardcoded.
//
//   center — EXPANDED: holds the active agent, and is the
//            active sub-section on load.
//   left   — EXPANDED, with Files/Changes/Commits open and Files active.
//   bottom — COLLAPSED, with one terminal open.
//   right  — COLLAPSED and empty; Actions/Skills/Notes default here only WHEN opened,
//            and nothing is open at first run.
//
// No splits. `center` is intentionally omitted from `expanded` — it is always
// expanded (see types.ts / isSectionExpandedAtom).

import { makeAgentPanelId } from "../registry/dynamicPanels.tsx";
import type { PanelId, SubSectionId } from "../sectionTypes.ts";
import type { WorkspaceLayoutState } from "./types.ts";

// The left explorer panels, in tab order, with Files active.
const DEFAULT_LEFT_PANEL_IDS: ReadonlyArray<PanelId> = ["files", "changes", "commits"];
const DEFAULT_ACTIVE_LEFT_PANEL_ID: PanelId = "files";

export type DefaultWorkspaceLayoutInputs = {
  // The active agent panel id (`agent:<taskId>`) placed into the center section.
  agentPanelId: PanelId;
  // The first-visit terminal panel id (`terminal:<wsId>:<index>`, indices start
  // at 1) placed into bottom. The terminal itself is seeded by the bootstrap;
  // this only records placement.
  terminalPanelId: PanelId;
};

export function buildDefaultWorkspaceLayout({
  agentPanelId,
  terminalPanelId,
}: DefaultWorkspaceLayoutInputs): WorkspaceLayoutState {
  return {
    placement: {
      [agentPanelId]: "center",
      // Derived from DEFAULT_LEFT_PANEL_IDS so the constant stays the single source
      // of truth: a panel added there gets a matching placement entry (open) here.
      ...Object.fromEntries(DEFAULT_LEFT_PANEL_IDS.map((id): [PanelId, SubSectionId] => [id, "left"])),
      [terminalPanelId]: "bottom",
    },
    order: {
      center: [agentPanelId],
      left: [...DEFAULT_LEFT_PANEL_IDS],
      bottom: [terminalPanelId],
    },
    activePanel: {
      center: agentPanelId,
      left: DEFAULT_ACTIVE_LEFT_PANEL_ID,
      bottom: terminalPanelId,
    },
    // center omitted — always expanded. left also starts expanded; right/bottom collapsed.
    expanded: {
      left: true,
      right: false,
      bottom: false,
    },
    splits: {},
    activeSubSection: "center",
  };
}

// The seeded default for a workspace that has NO agents yet: the standard default
// arrangement with the center left empty (its empty state offers the add-panel
// quick actions). Built by stripping a placeholder center panel from the standard
// default so the two arrangements cannot drift structurally.
export function buildAgentlessDefaultLayout(terminalPanelId: PanelId): WorkspaceLayoutState {
  const placeholderPanelId = makeAgentPanelId("placeholder");
  const layout = buildDefaultWorkspaceLayout({ agentPanelId: placeholderPanelId, terminalPanelId });
  const placement = { ...layout.placement };
  delete placement[placeholderPanelId];
  const activePanel = { ...layout.activePanel };
  delete activePanel.center;
  return { ...layout, placement, activePanel, order: { ...layout.order, center: [] } };
}
