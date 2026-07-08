// The workspace sidebar's visible ordering, in one place so the rendered rail and
// keyboard workspace cycling (Meta+] / Meta+[) can never disagree: workspaces are
// grouped by repo (project), and both the groups and the workspaces within them
// render in the user's stored drag order first (sidebarOrder in the global layout
// snapshot), with anything not yet reordered following alphabetically — the
// default order a user reads top-to-bottom before ever dragging.

import { arrayMove } from "@dnd-kit/sortable";
import { atom } from "jotai";
import { selectAtom } from "jotai/utils";

import type { Project, Workspace } from "~/api";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import type { SidebarOrderState } from "~/components/sections/persistence/types.ts";
import { globalLayoutAtom } from "~/components/sections/sectionAtoms.ts";

// A repo (project) and the workspaces that live in it, in visible order.
// SidebarRepoGroup renders one of these.
export type RepoGroup = {
  projectId: string;
  name: string;
  workspaces: ReadonlyArray<Workspace>;
};

const EMPTY_SIDEBAR_ORDER: SidebarOrderState = { repos: [], workspaces: {} };

// Stored-first ordering: items whose keys appear in `storedKeys` come first, in
// that stored order; the rest keep their incoming (alphabetical) order after them.
// Stored keys that no longer resolve to an item are skipped, so deletions never
// require cleaning the stored list; a key stored twice (a hand-edited or corrupt
// snapshot) takes its first slot only, so an item is never rendered twice.
function applyStoredOrder<T>(
  items: ReadonlyArray<T>,
  storedKeys: ReadonlyArray<string> | undefined,
  keyOf: (item: T) => string,
): Array<T> {
  if (storedKeys === undefined || storedKeys.length === 0) {
    return [...items];
  }
  // Taking each matched item OUT of the map makes duplicate stored keys miss on
  // their second occurrence, and leaves the map holding exactly the unstored items.
  const remainingByKey = new Map(items.map((item) => [keyOf(item), item]));
  const stored: Array<T> = [];
  for (const key of storedKeys) {
    const item = remainingByKey.get(key);
    if (item !== undefined) {
      stored.push(item);
      remainingByKey.delete(key);
    }
  }
  const unstored = items.filter((item) => remainingByKey.has(keyOf(item)));
  return [...stored, ...unstored];
}

// Build the sidebar's repo groups and apply the stored drag order. Seeds a group
// for every known project first, so a repo with no workspaces still shows (e.g.
// one just added, before its first workspace is created), then files each
// workspace under its project. A workspace whose project record hasn't loaded yet
// falls back to an "Other" group name (see the `?? "Other"` below) so nothing
// disappears.
export function groupWorkspacesByRepo(
  workspaces: ReadonlyArray<Workspace>,
  projects: ReadonlyArray<Project>,
  order: SidebarOrderState = EMPTY_SIDEBAR_ORDER,
): ReadonlyArray<RepoGroup> {
  const projectsById = new Map(projects.map((project) => [project.objectId, project]));
  const byProject = new Map<string, Array<Workspace>>();
  for (const project of projects) {
    byProject.set(project.objectId, []);
  }

  for (const ws of workspaces) {
    const list = byProject.get(ws.projectId) ?? [];
    list.push(ws);
    byProject.set(ws.projectId, list);
  }
  const groups = [...byProject.entries()]
    .map(([projectId, wsList]) => ({
      projectId,
      name: projectsById.get(projectId)?.name ?? "Other",
      workspaces: applyStoredOrder(
        wsList.sort((a, b) => (a.description ?? "").localeCompare(b.description ?? "")),
        order.workspaces[projectId],
        (ws) => ws.objectId,
      ),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
  return applyStoredOrder(groups, order.repos, (group) => group.projectId);
}

// The stored drag order, sliced so ordering only recomputes when a reorder actually
// lands — not on every other global-layout write (sidebar resize, section drags).
const sidebarOrderAtom = selectAtom(globalLayoutAtom, (global) => global.sidebarOrder);

// The sidebar's repo groups in render order. WorkspaceSidebar renders these.
// "Repo group" = one repo (project) section and its workspaces — distinct from
// the backend WorkspaceGroup entity (user-created groups WITHIN a repo).
export const sidebarRepoGroupsAtom = atom<ReadonlyArray<RepoGroup>>((get) =>
  groupWorkspacesByRepo(get(workspacesArrayAtom) ?? [], get(projectsArrayAtom), get(sidebarOrderAtom)),
);

// The sidebar's workspaces flattened into their visible top-to-bottom order, so
// keyboard cycling steps through the same list the user sees.
export const sidebarOrderedWorkspacesAtom = atom<ReadonlyArray<Workspace>>((get) =>
  get(sidebarRepoGroupsAtom).flatMap((group) => group.workspaces),
);

// Commit a workspace-row drop: move the dragged workspace to the drop target's slot
// within its repo group and store the group's full resulting order (materialized
// from the current visible order, so a partially-stored group resolves to exactly
// what the user saw when they dropped).
export const reorderSidebarWorkspaceAtom = atom(
  null,
  (get, set, params: { projectId: string; activeWorkspaceId: string; overWorkspaceId: string }) => {
    const group = get(sidebarRepoGroupsAtom).find((candidate) => candidate.projectId === params.projectId);
    if (group === undefined) {
      return;
    }
    const ids = group.workspaces.map((ws) => ws.objectId);
    const from = ids.indexOf(params.activeWorkspaceId);
    const to = ids.indexOf(params.overWorkspaceId);
    if (from === -1 || to === -1 || from === to) {
      return;
    }
    const next = arrayMove(ids, from, to);
    set(globalLayoutAtom, (prev) => ({
      ...prev,
      sidebarOrder: {
        ...prev.sidebarOrder,
        workspaces: { ...prev.sidebarOrder.workspaces, [params.projectId]: next },
      },
    }));
  },
);

// Commit a repo-group drop: same materialize-the-visible-order contract as
// reorderSidebarWorkspaceAtom, for the group list.
export const reorderSidebarRepoGroupAtom = atom(
  null,
  (get, set, params: { activeProjectId: string; overProjectId: string }) => {
    const ids = get(sidebarRepoGroupsAtom).map((group) => group.projectId);
    const from = ids.indexOf(params.activeProjectId);
    const to = ids.indexOf(params.overProjectId);
    if (from === -1 || to === -1 || from === to) {
      return;
    }
    set(globalLayoutAtom, (prev) => ({
      ...prev,
      sidebarOrder: { ...prev.sidebarOrder, repos: arrayMove(ids, from, to) },
    }));
  },
);
