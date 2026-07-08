/**
 * TanStack Query mutation hooks for workspace-group operations.
 *
 * Group state lives in the Jotai atoms in `atoms/workspaceGroups.ts`; the
 * unified stream is the authoritative writer. These hooks follow the task
 * mutation pattern in `./index.ts`, adapted to that store:
 *
 * - Rename/recolor is a field flip on an entity the client already holds, so
 *   it writes optimistically: `onMutate` snapshots the group plus its stream
 *   sync-version; `onError` restores the snapshot only if the version is
 *   unchanged (a WS frame that landed mid-request holds server truth and must
 *   win). `onSuccess` never writes — the stream delivers the committed value.
 * - Create, add/remove member, and ungroup have no optimistic write. Create
 *   materializes server-assigned facts (id, "Group N" name, palette color);
 *   the others flip `Workspace.groupId`, which lives in the workspace store
 *   and is projected there only by the stream. For all of them the failure
 *   path is the mutation's own error state (nothing was written locally, so
 *   nothing can be left stale), and success streams in.
 *
 * Every endpoint 409s with error code `workspace_groups_disabled` when the
 * `enable_workspace_groups` experiment is off; the client throws, so callers
 * see it on the mutation's error state like any other failure.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { useStore } from "jotai";

import type { WorkspaceGroup, WorkspaceGroupResponse } from "../../../api";
import {
  addWorkspaceGroupMember,
  createWorkspaceGroup,
  removeWorkspaceGroupMember,
  ungroupWorkspaceGroup,
  updateWorkspaceGroup,
} from "../../../api";
import { getWorkspaceGroupSyncVersion, workspaceGroupAtomFamily } from "../atoms/workspaceGroups.ts";

type JotaiStore = ReturnType<typeof useStore>;

export type WorkspaceGroupMutationContext = {
  prev: WorkspaceGroup | null;
  syncVersion: number;
};

/** Snapshot the stored group and, when it exists, replace it with `update(prev)`. */
export const applyOptimisticWorkspaceGroupUpdate = (
  store: JotaiStore,
  groupId: string,
  update: (prev: WorkspaceGroup) => WorkspaceGroup,
): WorkspaceGroupMutationContext => {
  const prev = store.get(workspaceGroupAtomFamily(groupId));
  if (prev !== null) {
    store.set(workspaceGroupAtomFamily(groupId), update(prev));
  }
  return { prev, syncVersion: getWorkspaceGroupSyncVersion(groupId) };
};

/**
 * Undo an optimistic update after a failed request, unless nothing was
 * written or a WS frame wrote the group in the meantime. Returns whether the
 * snapshot was restored.
 */
export const rollbackOptimisticWorkspaceGroupUpdate = (
  store: JotaiStore,
  groupId: string,
  ctx: WorkspaceGroupMutationContext | undefined,
): boolean => {
  if (!ctx?.prev || getWorkspaceGroupSyncVersion(groupId) !== ctx.syncVersion) {
    return false;
  }
  store.set(workspaceGroupAtomFamily(groupId), ctx.prev);
  return true;
};

type CreateWorkspaceGroupVars = {
  projectId: string;
  workspaceIds: ReadonlyArray<string>;
  name?: string;
  color?: string;
};

/**
 * Create a group around one or more initial member workspaces (groups never
 * exist empty). Resolves to the created group so callers can act on the
 * server-assigned id (e.g. focus the new card for rename).
 */
export const useCreateWorkspaceGroupMutation = (): UseMutationResult<
  WorkspaceGroupResponse,
  Error,
  CreateWorkspaceGroupVars,
  unknown
> =>
  useMutation({
    mutationFn: async (vars: CreateWorkspaceGroupVars) => {
      const response = await createWorkspaceGroup({
        body: {
          projectId: vars.projectId,
          workspaceIds: [...vars.workspaceIds],
          name: vars.name,
          color: vars.color,
        },
      });
      return response.data;
    },
  });

type UpdateWorkspaceGroupVars = { groupId: string; name?: string; color?: string };

/** Optimistically rename and/or recolor a group. Omitted fields are left unchanged. */
export const useUpdateWorkspaceGroupMutation = (): UseMutationResult<
  unknown,
  Error,
  UpdateWorkspaceGroupVars,
  WorkspaceGroupMutationContext
> => {
  const store = useStore();
  return useMutation({
    mutationFn: (vars: UpdateWorkspaceGroupVars) =>
      updateWorkspaceGroup({
        path: { group_id: vars.groupId },
        body: { name: vars.name, color: vars.color },
      }),
    onMutate: (vars): WorkspaceGroupMutationContext =>
      applyOptimisticWorkspaceGroupUpdate(store, vars.groupId, (prev) => ({
        ...prev,
        ...(vars.name !== undefined ? { name: vars.name } : {}),
        ...(vars.color !== undefined ? { color: vars.color } : {}),
      })),
    onError: (_e, vars, ctx): void => {
      rollbackOptimisticWorkspaceGroupUpdate(store, vars.groupId, ctx);
    },
  });
};

type WorkspaceGroupMemberVars = { groupId: string; workspaceId: string };

/** Add a workspace (from the group's project) to a group. */
export const useAddWorkspaceGroupMemberMutation = (): UseMutationResult<
  unknown,
  Error,
  WorkspaceGroupMemberVars,
  unknown
> =>
  useMutation({
    mutationFn: (vars: WorkspaceGroupMemberVars) =>
      addWorkspaceGroupMember({
        path: { group_id: vars.groupId },
        body: { workspaceId: vars.workspaceId },
      }),
  });

/**
 * Remove a workspace from a group, releasing it to the repo's loose list.
 * Removing the last member dissolves the group server-side (empty groups
 * must not exist), which streams back as a group deletion.
 */
export const useRemoveWorkspaceGroupMemberMutation = (): UseMutationResult<
  unknown,
  Error,
  WorkspaceGroupMemberVars,
  unknown
> =>
  useMutation({
    mutationFn: (vars: WorkspaceGroupMemberVars) =>
      removeWorkspaceGroupMember({
        path: { group_id: vars.groupId, workspace_id: vars.workspaceId },
      }),
  });

type UngroupWorkspaceGroupVars = { groupId: string };

/**
 * Dissolve a group, releasing all members back to the repo's loose list.
 * Never deletes workspaces.
 */
export const useUngroupWorkspaceGroupMutation = (): UseMutationResult<
  unknown,
  Error,
  UngroupWorkspaceGroupVars,
  unknown
> =>
  useMutation({
    mutationFn: (vars: UngroupWorkspaceGroupVars) => ungroupWorkspaceGroup({ path: { group_id: vars.groupId } }),
  });
