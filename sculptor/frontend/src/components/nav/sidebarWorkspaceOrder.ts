// The workspace sidebar's visible ordering, in one place so the rendered rail and
// keyboard workspace cycling (Meta+] / Meta+[) can never disagree: workspaces are
// grouped by repo (project) with the groups sorted by name, and within each group
// sorted alphabetically by description — the order a user reads top-to-bottom.

import { atom } from "jotai";

import type { Project, Workspace } from "~/api";
import { projectsArrayAtom } from "~/common/state/atoms/projects.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";

import type { RepoGroup } from "./SidebarRepoGroup.tsx";

// Build the sidebar's repo groups. Seeds a group for every known project first,
// so a repo with no workspaces still shows (e.g. one just added, before its first
// workspace is created), then files each workspace under its project. A workspace
// whose project record hasn't loaded yet falls back to an "Other" group name (see
// the `?? "Other"` below) so nothing disappears.
export function groupWorkspacesByRepo(
  workspaces: ReadonlyArray<Workspace>,
  projects: ReadonlyArray<Project>,
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
  return [...byProject.entries()]
    .map(([projectId, wsList]) => ({
      projectId,
      name: projectsById.get(projectId)?.name ?? "Other",
      workspaces: wsList.sort((a, b) => (a.description ?? "").localeCompare(b.description ?? "")),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// The sidebar's repo groups in render order. WorkspaceSidebar renders these.
export const sidebarWorkspaceGroupsAtom = atom<ReadonlyArray<RepoGroup>>((get) =>
  groupWorkspacesByRepo(get(workspacesArrayAtom) ?? [], get(projectsArrayAtom)),
);

// The sidebar's workspaces flattened into their visible top-to-bottom order, so
// keyboard cycling steps through the same list the user sees.
export const sidebarOrderedWorkspacesAtom = atom<ReadonlyArray<Workspace>>((get) =>
  get(sidebarWorkspaceGroupsAtom).flatMap((group) => group.workspaces),
);
