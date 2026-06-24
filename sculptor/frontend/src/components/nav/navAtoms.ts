import { atomWithStorage } from "jotai/utils";

// Per-repo collapse state for the workspace sidebar's repo groups, keyed by
// project id. Persisted to localStorage so a collapsed repo stays collapsed
// across reloads. Sidebar width/collapsed live separately in
// `~/components/layout/sidebarAtoms.ts` (global layout snapshot); only the
// repo-group state is owned here.
export const collapsedRepoGroupsAtom = atomWithStorage<Record<string, boolean>>(
  "sculptor-collapsed-repo-groups",
  {},
  undefined,
  { getOnInit: true },
);
