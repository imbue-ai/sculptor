import { atomWithStorage } from "jotai/utils";

// Vertical-nav-sidebar UI state. Persisted to localStorage (REQ-PERSIST-4).
//
// NOTE: the spec scopes sidebar-collapsed and repo-group-collapse per-workspace
// (REQ-PERSIST-1). For this spike they are persisted globally — the sidebar is
// global chrome shown on every route (including Home/Settings), so a global
// collapse state is simpler and reads more naturally. Per-workspace scoping is
// a straightforward follow-up via the usePerWorkspacePanelLayout mechanism.

/** Whether the vertical nav sidebar is collapsed (hidden entirely). (REQ-NAV-7) */
export const navSidebarCollapsedAtom = atomWithStorage<boolean>("sculptor-nav-sidebar-collapsed", false, undefined, {
  getOnInit: true,
});

/** Per-repo collapsed state for the repo groups, keyed by project id. (REQ-NAV-3) */
export const collapsedRepoGroupsAtom = atomWithStorage<Record<string, boolean>>(
  "sculptor-nav-collapsed-repos",
  {},
  undefined,
  { getOnInit: true },
);
