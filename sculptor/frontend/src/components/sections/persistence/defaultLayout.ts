// The default workspace arrangement, seeded on a workspace's FIRST visit
// (goals.md → "Default layout"; SEC-01..04). It is built here as a pure function so
// it can be unit-tested and reused; the dynamic agent/terminal ids are resolved by
// the caller (the Task 6.2 bootstrap) from the active task and the first-visit
// seeded terminal — never hardcoded.
//
//   center — the only EXPANDED section: holds the active agent (SEC-01), and is the
//            active sub-section on load.
//   left   — COLLAPSED, with Files/Changes/Commits open and Files active (SEC-02).
//   bottom — COLLAPSED, with one terminal open (SEC-03).
//   right  — COLLAPSED and empty; Actions/Skills/Notes default here only WHEN opened,
//            and nothing is open at first run (SEC-04).
//
// No splits. `center` is intentionally omitted from `expanded` — it is always
// expanded (see types.ts / isSectionExpandedAtom).

import type { PanelId } from "../sectionTypes.ts";
import type { WorkspaceLayoutState } from "./types.ts";

// The left explorer panels, in tab order, with Files active (SEC-02).
export const DEFAULT_LEFT_PANEL_IDS: ReadonlyArray<PanelId> = ["files", "changes", "commits"];
export const DEFAULT_ACTIVE_LEFT_PANEL_ID: PanelId = "files";

export type DefaultWorkspaceLayoutInputs = {
  // The active agent panel id (`agent:<taskId>`) placed into the center section.
  agentPanelId: PanelId;
  // The first-visit terminal panel id (`terminal:<wsId>:0`) placed into bottom. The
  // terminal itself is seeded by the Task 6.2 bootstrap; this only records placement.
  terminalPanelId: PanelId;
};

export function buildDefaultWorkspaceLayout({
  agentPanelId,
  terminalPanelId,
}: DefaultWorkspaceLayoutInputs): WorkspaceLayoutState {
  return {
    placement: {
      [agentPanelId]: "center",
      files: "left",
      changes: "left",
      commits: "left",
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
    // center omitted — always expanded; the other three start collapsed.
    expanded: {
      left: false,
      right: false,
      bottom: false,
    },
    splits: {},
    activeSubSection: "center",
  };
}
