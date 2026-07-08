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

// The sidebar's workspaces flattened into their visible top-to-bottom order, so
// keyboard cycling steps through the same list the user sees.
export const sidebarOrderedWorkspacesAtom = atom<ReadonlyArray<Workspace>>((get) =>
  get(sidebarRepoGroupsAtom).flatMap((group) => group.workspaces),
);

// Commit a drop within a repo section's mixed children lane: move the dragged
// child (a loose workspace row or a whole group card) to the drop target's slot
// and store the section's full resulting child order (materialized from the
// current visible order, so a partially-stored lane resolves to exactly what
// the user saw when they dropped).
export const reorderSidebarRepoChildAtom = atom(
  null,
  (get, set, params: { projectId: string; activeChildId: string; overChildId: string }) => {
    const group = get(sidebarRepoGroupsAtom).find((candidate) => candidate.projectId === params.projectId);
    if (group === undefined) {
      return;
    }
    const ids = group.children.map(repoSectionChildKey);
    const from = ids.indexOf(params.activeChildId);
    const to = ids.indexOf(params.overChildId);
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

// Commit a member-row drop within one group card: same
// materialize-the-visible-order contract as reorderSidebarRepoChildAtom, for
// the group's member lane.
export const reorderWorkspaceGroupMemberAtom = atom(
  null,
  (get, set, params: { projectId: string; groupId: string; activeWorkspaceId: string; overWorkspaceId: string }) => {
    const group = get(sidebarRepoGroupsAtom).find((candidate) => candidate.projectId === params.projectId);
    const groupChild = group?.children.find(
      (child) => child.kind === "group" && child.group.objectId === params.groupId,
    );
    if (groupChild === undefined || groupChild.kind !== "group") {
      return;
    }
    const ids = groupChild.members.map((member) => member.objectId);
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
        groupMembers: { ...prev.sidebarOrder.groupMembers, [params.groupId]: next },
      },
    }));
  },
);

// Where a membership-changing drop placed the workspace: into a group's member
// lane (before one of its members, or appended), or into the repo section's
// mixed lane as a loose row (before one of the section's children, or appended).
export type WorkspaceMembershipDropTarget =
  | { kind: "group"; groupId: string; beforeWorkspaceId?: string }
  | { kind: "loose"; beforeChildId?: string };

// Commit the ORDER half of a membership-changing drop (loose→group,
// group→loose, group→group). Membership itself is a backend fact that the
// caller flips through the canonical mutation; this atom runs only after that
// mutation succeeds, so a rejected drop never strands the workspace in a lane
// for a group it isn't in. It materializes the destination lane from the
// CURRENT visible order — the workspace is excluded first and re-inserted at
// the drop anchor, which makes the write correct whether the confirming stream
// frame has already landed or not (the source lanes need no cleanup: a lane id
// that no longer resolves to a child/member is skipped on read).
export const commitWorkspaceMembershipOrderAtom = atom(
  null,
  (get, set, params: { projectId: string; workspaceId: string; target: WorkspaceMembershipDropTarget }) => {
    const group = get(sidebarRepoGroupsAtom).find((candidate) => candidate.projectId === params.projectId);
    if (group === undefined) {
      return;
    }

    if (params.target.kind === "group") {
      const { groupId, beforeWorkspaceId } = params.target;
      const groupChild = group.children.find((child) => child.kind === "group" && child.group.objectId === groupId);
      const ids = (groupChild?.kind === "group" ? groupChild.members : [])
        .map((member) => member.objectId)
        .filter((id) => id !== params.workspaceId);
      const anchor = beforeWorkspaceId === undefined ? -1 : ids.indexOf(beforeWorkspaceId);
      ids.splice(anchor === -1 ? ids.length : anchor, 0, params.workspaceId);
      set(globalLayoutAtom, (prev) => ({
        ...prev,
        sidebarOrder: {
          ...prev.sidebarOrder,
          groupMembers: { ...prev.sidebarOrder.groupMembers, [groupId]: ids },
        },
      }));
      return;
    }
    const { beforeChildId } = params.target;
    const ids = group.children.map(repoSectionChildKey).filter((id) => id !== params.workspaceId);
    const anchor = beforeChildId === undefined ? -1 : ids.indexOf(beforeChildId);
    ids.splice(anchor === -1 ? ids.length : anchor, 0, params.workspaceId);
    set(globalLayoutAtom, (prev) => ({
      ...prev,
      sidebarOrder: {
        ...prev.sidebarOrder,
        workspaces: { ...prev.sidebarOrder.workspaces, [params.projectId]: ids },
      },
    }));
  },
);

// Commit a repo-group drop: same materialize-the-visible-order contract as
// reorderSidebarRepoChildAtom, for the repo list.
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
