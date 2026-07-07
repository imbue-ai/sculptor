import { atom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

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

// One project's collapse flag, sliced out of the shared record so a repo group
// only re-renders when its own state flips — toggling any sibling would
// otherwise re-render every group subscribed to the whole record.
export const isRepoCollapsedAtomFamily = atomFamily((projectId: string) =>
  atom((get) => get(collapsedRepoGroupsAtom)[projectId] ?? false),
);

// True while a sidebar row or repo group is being dragged. Transient (never
// persisted); the workspace peek overlay reads it to stay closed mid-drag — the
// pointer sweeps across rows while sorting, which would otherwise pop the peek.
export const isSidebarDragActiveAtom = atom(false);
