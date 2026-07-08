// Composes one repo section's children when workspace groups are enabled:
// the repo's workspace-group cards (with their member rows) plus the loose
// workspaces that remain directly under the repo header. Pure, so the split
// is unit-testable; SidebarRepoGroup is the only render-path consumer.

import type { Workspace, WorkspaceGroup } from "~/api";

export type WorkspaceGroupWithMembers = {
  group: WorkspaceGroup;
  members: ReadonlyArray<Workspace>;
};

export type RepoSectionChildren = {
  /** The repo's group cards, in the order the groups were given (creation order). */
  groupsWithMembers: ReadonlyArray<WorkspaceGroupWithMembers>;
  /** Workspaces not claimed by any given group, in the order they were given (stored drag order). */
  looseWorkspaces: ReadonlyArray<Workspace>;
};

/**
 * Split a repo's workspaces into group members and the loose remainder.
 *
 * Members render in description order (the sidebar's pre-drag default order)
 * inside their card. A workspace whose `groupId` doesn't match any given group
 * (a dissolved group, or one whose stream frame hasn't arrived) stays loose,
 * so a membership race can never make a workspace disappear from the rail.
 * A group none of the workspaces claims is dropped: empty groups don't exist
 * server-side, so an empty card could only ever be a mid-stream flicker.
 */
export const composeRepoSectionChildren = (
  workspaces: ReadonlyArray<Workspace>,
  groups: ReadonlyArray<WorkspaceGroup>,
): RepoSectionChildren => {
  if (groups.length === 0) {
    return { groupsWithMembers: [], looseWorkspaces: workspaces };
  }

  const membersByGroupId = new Map<string, Array<Workspace>>(groups.map((group) => [group.objectId, []]));
  const looseWorkspaces: Array<Workspace> = [];
  for (const workspace of workspaces) {
    const members = workspace.groupId != null ? membersByGroupId.get(workspace.groupId) : undefined;
    if (members === undefined) {
      looseWorkspaces.push(workspace);
    } else {
      members.push(workspace);
    }
  }

  const groupsWithMembers = groups
    .map((group) => ({
      group,
      members: (membersByGroupId.get(group.objectId) ?? []).sort(
        (a, b) => (a.description ?? "").localeCompare(b.description ?? "") || a.objectId.localeCompare(b.objectId),
      ),
    }))
    .filter(({ members }) => members.length > 0);
  return { groupsWithMembers, looseWorkspaces };
};
