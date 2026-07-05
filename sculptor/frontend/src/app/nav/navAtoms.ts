import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

// Per-repo collapse state for the workspace sidebar's repo groups, keyed by
// project id. Persisted to localStorage so a collapsed repo stays collapsed
// across reloads. Sidebar width/collapsed live separately in
// `~/pages/workspace/layout/atoms/sidebar.ts` (global layout snapshot); only the
// repo-group state is owned here.
export const collapsedRepoGroupsAtom = atomWithStorage<Record<string, boolean>>(
  "sculptor-collapsed-repo-groups",
  {},
  undefined,
  { getOnInit: true },
);

// One project's collapse flag, sliced out of the shared record so a repo group
// only re-renders when its own state flips — toggling any sibling would
// otherwise re-render every group subscribed to the whole record.
export const isRepoCollapsedAtomFamily = atomFamily((projectId: string) =>
  atom((get) => get(collapsedRepoGroupsAtom)[projectId] ?? false),
);
