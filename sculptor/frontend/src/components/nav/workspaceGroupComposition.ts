// Composes one repo section's children: workspace-group cards (with their
// member rows) and loose workspace rows, interleaved in ONE re-orderable
// sequence — the section's mixed lane. Workspace ids and group ids share the
// stored lane (distinguishable by their ws_/wsg_ id prefixes); member order
// per group lives in its own stored lane. Everything here is pure so the
// ordering is unit-testable; sidebarWorkspaceOrder.ts is the only render-path
// consumer.

import type { Workspace, WorkspaceGroup } from "~/api";

// Stored-first ordering: items whose keys appear in `storedKeys` come first, in
// that stored order; the rest keep their incoming (alphabetical) order after them.
// Stored keys that no longer resolve to an item are skipped, so deletions never
// require cleaning the stored list; a key stored twice (a hand-edited or corrupt
// snapshot) takes its first slot only, so an item is never rendered twice.
export function applyStoredOrder<T>(
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

// One entry of a repo section's mixed children lane: a loose workspace row or
// a workspace-group card wrapping its member rows (already in render order).
export type RepoSectionChild =
  | { kind: "workspace"; workspace: Workspace }
  | { kind: "group"; group: WorkspaceGroup; members: ReadonlyArray<Workspace> };

/** The child's key in the stored mixed lane: the workspace id or the group id. */
export const repoSectionChildKey = (child: RepoSectionChild): string =>
  child.kind === "workspace" ? child.workspace.objectId : child.group.objectId;

/** The child's display name, which drives the pre-drag alphabetical default order. */
const repoSectionChildName = (child: RepoSectionChild): string =>
  (child.kind === "workspace" ? child.workspace.description : child.group.name) ?? "";

/**
 * Compose a repo section's children in visible order.
 *
 * Loose workspaces and group cards interleave in one lane: never-dragged
 * children default to alphabetical by display name (workspace description /
 * group name), and the stored mixed lane's ids render first in stored order.
 * Members within a group follow the same convention against their group's
 * stored member lane.
 *
 * A workspace whose `groupId` matches no given group (a dissolved group, or
 * one whose stream frame hasn't arrived) stays loose, so a membership race can
 * never make a workspace disappear from the rail. A group none of the
 * workspaces claims is dropped: empty groups don't exist server-side, so an
 * empty card could only ever be a mid-stream flicker. With no groups given
 * (the feature flag off), the lane degrades to a plain workspace order — any
 * stored group ids resolve to nothing and are skipped.
 */
export const composeRepoSectionChildren = (
  workspaces: ReadonlyArray<Workspace>,
  groups: ReadonlyArray<WorkspaceGroup>,
  storedChildOrder: ReadonlyArray<string> | undefined,
  storedMemberOrders: Partial<Record<string, Array<string>>> | undefined,
): ReadonlyArray<RepoSectionChild> => {
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

  const children: Array<RepoSectionChild> = [
    ...looseWorkspaces.map((workspace): RepoSectionChild => ({ kind: "workspace", workspace })),
    ...groups
      .map((group): RepoSectionChild => {
        const members = (membersByGroupId.get(group.objectId) ?? []).sort(
          (a, b) => (a.description ?? "").localeCompare(b.description ?? "") || a.objectId.localeCompare(b.objectId),
        );
        return {
          kind: "group",
          group,
          members: applyStoredOrder(members, storedMemberOrders?.[group.objectId], (member) => member.objectId),
        };
      })
      .filter((child) => child.kind === "group" && child.members.length > 0),
  ];
  // Sort the WHOLE candidate list (not just the unstored tail) so the fallback
  // order is deterministic regardless of how the inputs arrived; the stored
  // lane then pulls its ids to the front.
  children.sort((a, b) => repoSectionChildName(a).localeCompare(repoSectionChildName(b)));
  return applyStoredOrder(children, storedChildOrder, repoSectionChildKey);
};
