// The workspace sidebar's visible ordering, in one place so the rendered rail and
// keyboard workspace cycling (Meta+] / Meta+[) can never disagree: workspaces are
// grouped by repo (project), and each repo section's children — loose workspace
// rows interleaved with workspace-group cards — render in the user's stored drag
// order first (sidebarOrder in the global layout snapshot), with anything not yet
// reordered following alphabetically — the default order a user reads
// top-to-bottom before ever dragging. The composition itself lives in
// workspaceGroupComposition.ts; this module binds it to the stores and owns the
// write atoms that commit drops.

import { arrayMove } from "@dnd-kit/sortable";
import { atom } from "jotai";
import { selectAtom } from "jotai/utils";

import type { Project, Workspace, WorkspaceGroup } from "~/api";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { isWorkspaceGroupsEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { workspaceGroupsArrayAtom } from "~/common/state/atoms/workspaceGroups.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import type { SidebarOrderState } from "~/components/sections/persistence/types.ts";
import { globalLayoutAtom } from "~/components/sections/sectionAtoms.ts";

import type { RepoSectionChild } from "./workspaceGroupComposition.ts";
import { applyStoredOrder, composeRepoSectionChildren, repoSectionChildKey } from "./workspaceGroupComposition.ts";

// A repo (project) and its children in visible order. SidebarRepoGroup renders
// one of these: `children` is the mixed lane it renders top-to-bottom, and
// `workspaces` is the same tree flattened (group members expanded in place) so
// keyboard cycling steps through exactly what the user sees.
export type RepoGroup = {
  projectId: string;
  name: string;
  children: ReadonlyArray<RepoSectionChild>;
  workspaces: ReadonlyArray<Workspace>;
};

const EMPTY_SIDEBAR_ORDER: SidebarOrderState = { repos: [], workspaces: {} };
const NO_WORKSPACE_GROUPS: ReadonlyArray<WorkspaceGroup> = [];

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
  workspaceGroups: ReadonlyArray<WorkspaceGroup> = NO_WORKSPACE_GROUPS,
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
    .map(([projectId, wsList]) => {
      const children = composeRepoSectionChildren(
        wsList,
        workspaceGroups.filter((group) => group.projectId === projectId),
        order.workspaces[projectId],
        order.groupMembers,
      );
      return {
        projectId,
        name: projectsById.get(projectId)?.name ?? "Other",
        children,
        workspaces: children.flatMap((child) => (child.kind === "workspace" ? [child.workspace] : child.members)),
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
  return applyStoredOrder(groups, order.repos, (group) => group.projectId);
}

// The stored drag order, sliced so ordering only recomputes when a reorder actually
// lands — not on every other global-layout write (sidebar resize, section drags).
const sidebarOrderAtom = selectAtom(globalLayoutAtom, (global) => global.sidebarOrder);

// The sidebar's repo groups in render order. WorkspaceSidebar renders these.
// "Repo group" = one repo (project) section and its children — distinct from
// the backend WorkspaceGroup entity (user-created groups WITHIN a repo).
// With the workspace-groups flag off this must not touch the group store at
// all (the conditional get skips the subscription), so the sidebar renders
// exactly the pre-groups tree.
export const sidebarRepoGroupsAtom = atom<ReadonlyArray<RepoGroup>>((get) =>
  groupWorkspacesByRepo(
    get(workspacesArrayAtom) ?? [],
    get(projectsArrayAtom),
    get(sidebarOrderAtom),
    get(isWorkspaceGroupsEnabledAtom) ? (get(workspaceGroupsArrayAtom) ?? NO_WORKSPACE_GROUPS) : NO_WORKSPACE_GROUPS,
  ),
);

// True while the first workspace snapshot is still in flight, so the sidebar can
// show a loading skeleton instead of a blank rail (e.g. right after a hard
// refresh, before the reconnecting WebSocket delivers the first frame).
//
// `workspacesArrayAtom` is `undefined` only until that first frame lands — the
// frame always writes an array, even an empty one — so this cleanly separates
// "not loaded yet" from "loaded and genuinely empty", a distinction the groups
// atom above deliberately erases with its `?? []` (keyboard cycling and drag
// ordering want a concrete array regardless).
export const isSidebarLoadingAtom = atom<boolean>((get) => get(workspacesArrayAtom) === undefined);

// The sidebar's workspaces flattened into their visible top-to-bottom order, so
// keyboard cycling steps through the same list the user sees.
export const sidebarOrderedWorkspacesAtom = atom<ReadonlyArray<Workspace>>((get) =>
  get(sidebarRepoGroupsAtom).flatMap((group) => group.workspaces),
);

// What commitSectionDropAtom overwrote, so a drop whose membership mutation
// the server later rejects can put the stored lanes back exactly (the
// membership flip itself is rolled back by the mutation hook). `undefined`
// lane values are meaningful: they mean "was never stored" and restore to that.
export type SectionOrderSnapshot = {
  projectId: string;
  childLane: Array<string> | undefined;
  memberLanes: Record<string, Array<string> | undefined>;
};

// Commit a drop's resulting order for one repo section: materialize the FULL
// projected tree — the mixed children lane plus every group's member lane — in
// one write, so the lanes always describe exactly what the user saw land
// (REQ-DND-7). Membership is a backend fact the caller flips through the
// canonical mutation alongside this write; a lane id whose membership write
// fails simply stops resolving and is skipped on read, and the returned
// snapshot lets the caller restore the previous lanes precisely.
export const commitSectionDropAtom = atom(
  null,
  (get, set, params: { projectId: string; children: ReadonlyArray<RepoSectionChild> }): SectionOrderSnapshot => {
    const prev = get(globalLayoutAtom).sidebarOrder;
    const snapshot: SectionOrderSnapshot = {
      projectId: params.projectId,
      childLane: prev.workspaces[params.projectId],
      memberLanes: {},
    };
    const nextMemberLanes: Record<string, Array<string>> = {};
    for (const child of params.children) {
      if (child.kind === "group") {
        snapshot.memberLanes[child.group.objectId] = prev.groupMembers?.[child.group.objectId];
        nextMemberLanes[child.group.objectId] = child.members.map((member) => member.objectId);
      }
    }
    set(globalLayoutAtom, (layout) => ({
      ...layout,
      sidebarOrder: {
        ...layout.sidebarOrder,
        workspaces: { ...layout.sidebarOrder.workspaces, [params.projectId]: params.children.map(repoSectionChildKey) },
        groupMembers: { ...layout.sidebarOrder.groupMembers, ...nextMemberLanes },
      },
    }));
    return snapshot;
  },
);

// Restore the lanes a commitSectionDropAtom write replaced (the drop's
// membership mutation failed). Writes back exactly the snapshot, including
// never-stored (`undefined`) lanes.
export const restoreSectionOrderAtom = atom(null, (_get, set, snapshot: SectionOrderSnapshot) => {
  set(globalLayoutAtom, (layout) => ({
    ...layout,
    sidebarOrder: {
      ...layout.sidebarOrder,
      workspaces: { ...layout.sidebarOrder.workspaces, [snapshot.projectId]: snapshot.childLane },
      groupMembers: { ...layout.sidebarOrder.groupMembers, ...snapshot.memberLanes },
    },
  }));
});

// Commit a repo-group drop: same materialize-the-visible-order contract as
// commitSectionDropAtom, for the repo list.
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
