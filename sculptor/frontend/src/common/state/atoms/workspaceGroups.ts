// Workspace groups: named, colored collections of workspaces within one repo
// (project). The backend owns the groups themselves and each workspace's
// membership (`Workspace.groupId`); both stream in over the unified WebSocket.
// This module is the single written store for group entities —
// `updateWorkspaceGroupsAtom` is the authoritative stream writer, and the
// optimistic rename/recolor path in `mutations/workspaceGroups.ts` is the only
// other writer (with a sync-version-guarded rollback). Everything else reads.

import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";
import { isEqual } from "lodash";

import type { Workspace, WorkspaceGroup } from "../../../api";
import { workspacesArrayAtom } from "./workspaces.ts";

/**
 * The group-by-id lookup and per-group store. Holds `null` for ids the stream
 * hasn't delivered (or has deleted). Written only by
 * `updateWorkspaceGroupsAtom` and the optimistic mutation helpers.
 */
export const workspaceGroupAtomFamily = atomFamily<string, PrimitiveAtom<WorkspaceGroup | null>>(() =>
  atom<WorkspaceGroup | null>(null),
);

/** `undefined` until the first stream frame carrying groups arrives. */
export const workspaceGroupIdsAtom = atom<ReadonlyArray<string> | undefined>(undefined);

export const workspaceGroupsArrayAtom = atom<ReadonlyArray<WorkspaceGroup> | undefined>((get) => {
  const groupIds = get(workspaceGroupIdsAtom);
  if (groupIds === undefined) {
    return undefined;
  }
  return groupIds
    .map((id) => get(workspaceGroupAtomFamily(id)))
    .filter((group): group is WorkspaceGroup => group !== null && !group.isDeleted);
});

/**
 * Per-group monotonic version, bumped on every authoritative stream write.
 * A failed optimistic mutation may only roll back while the version it
 * snapshotted is still current — a bump means a WS frame holds server truth
 * and the stale snapshot must lose (see `mutations/workspaceGroups.ts`).
 */
const workspaceGroupSyncVersions = new Map<string, number>();

export const getWorkspaceGroupSyncVersion = (groupId: string): number => workspaceGroupSyncVersions.get(groupId) ?? 0;

/** Versions live in a module-level map, so tests must reset them explicitly. */
export const resetWorkspaceGroupSyncVersionsForTesting = (): void => {
  workspaceGroupSyncVersions.clear();
};

/**
 * The unified stream's projection of workspace-group frames into the store.
 * Frames are deltas: only changed groups arrive (the initial snapshot carries
 * all of them). Deleted groups are nulled out and dropped from the id list —
 * ungrouping soft-deletes the group server-side, so a deletion frame is how
 * an ungroup (or auto-dissolve) reaches the UI.
 */
export const updateWorkspaceGroupsAtom = atom(null, (get, set, groups: ReadonlyArray<WorkspaceGroup>) => {
  const currentGroupIds = new Set(get(workspaceGroupIdsAtom) ?? []);

  groups.forEach((incoming) => {
    // Every delivered group is authoritative — bump even when the value write
    // below is skipped as equal, so an in-flight mutation's rollback yields.
    workspaceGroupSyncVersions.set(incoming.objectId, getWorkspaceGroupSyncVersion(incoming.objectId) + 1);

    if (incoming.isDeleted) {
      currentGroupIds.delete(incoming.objectId);
      set(workspaceGroupAtomFamily(incoming.objectId), null);
      return;
    }

    // Skip the write when nothing changed: stream frames carry fresh objects,
    // and an unconditional write would re-render each group's subscribers per
    // frame. Deep equality so a new backend field is never silently dropped.
    const previous = get(workspaceGroupAtomFamily(incoming.objectId));
    if (previous === null || !isEqual(previous, incoming)) {
      set(workspaceGroupAtomFamily(incoming.objectId), incoming);
    }
    currentGroupIds.add(incoming.objectId);
  });

  // Only write the id LIST when membership actually changed, mirroring the
  // per-group writes. The first frame always writes: undefined → array marks
  // the list loaded, even when it is empty.
  const previousIds = get(workspaceGroupIdsAtom);
  const nextIds = Array.from(currentGroupIds);
  if (previousIds === undefined || !isEqual([...previousIds].sort(), [...nextIds].sort())) {
    set(workspaceGroupIdsAtom, nextIds);
  }
});

/**
 * The live groups of one project, in creation order (createdAt, objectId as
 * tiebreak) — the order the server's "Group N" names were assigned in. Visual
 * sidebar order is the layout's concern, not this atom's. Equality-guarded so
 * per-repo subscribers only re-render when their own project's groups change.
 */
export const workspaceGroupsForProjectAtomFamily = atomFamily((projectId: string) =>
  selectAtom(
    workspaceGroupsArrayAtom,
    (groups): ReadonlyArray<WorkspaceGroup> =>
      (groups ?? [])
        .filter((group) => group.projectId === projectId)
        .sort((a, b) => (a.createdAt ?? "").localeCompare(b.createdAt ?? "") || a.objectId.localeCompare(b.objectId)),
    isEqual,
  ),
);

/**
 * The member workspaces of one group. Membership truth lives on the workspace
 * (`Workspace.groupId`), so this is a join over the workspace store — a group
 * never lists a deleted workspace because `workspacesArrayAtom` already
 * filters those out. Order is the workspace store's order; visual member
 * order inside a group card is the layout's concern.
 */
export const workspaceGroupMembersAtomFamily = atomFamily((groupId: string) =>
  selectAtom(
    workspacesArrayAtom,
    (workspaces): ReadonlyArray<Workspace> => (workspaces ?? []).filter((ws) => ws.groupId === groupId),
    isEqual,
  ),
);
