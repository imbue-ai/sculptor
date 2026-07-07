/**
 * TanStack Query mutation hooks for agent-task operations.
 *
 * The query cache is the single written store for task state: the WS bridge
 * writes authoritative frames, these hooks write optimistic updates, and
 * `useTaskQueryMirror` projects the cache into the legacy Jotai atoms — so no
 * hook here touches Jotai.
 *
 * Optimistic pattern: `onMutate` snapshots the cache entry plus the task's
 * WS sync-version; `onError` restores the snapshot only if the version is
 * unchanged. If a WS frame wrote the task while the request was in flight,
 * the frame holds server truth (whether or not the mutation committed) and
 * the stale snapshot must lose. `onSuccess` never writes: a successful
 * mutation changes the task server-side, so the delta stream delivers the
 * authoritative value.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../../api";
import {
  markWorkspaceAgentRead,
  markWorkspaceAgentUnread,
  renameWorkspaceAgent,
  restoreWorkspaceAgent,
} from "../../../api";
import { getTaskSyncVersion, queryClient, taskQueryKey } from "../../queryClient.ts";
import { clearUnreadOverride, setUnreadOverride } from "../atoms/unreadOverrides";

export type TaskMutationContext = {
  prev: CodingAgentTaskView | null | undefined;
  syncVersion: number;
};

/** Snapshot the cached task and, when it exists, replace it with `update(prev)`. */
export const applyOptimisticTaskUpdate = (
  agentId: string,
  update: (prev: CodingAgentTaskView) => CodingAgentTaskView,
): TaskMutationContext => {
  const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(agentId));
  if (prev) {
    queryClient.setQueryData(taskQueryKey(agentId), update(prev));
  }
  return { prev, syncVersion: getTaskSyncVersion(agentId) };
};

/**
 * Undo an optimistic update after a failed request, unless nothing was
 * written or a WS frame wrote the task in the meantime. Returns whether the
 * snapshot was restored.
 */
export const rollbackOptimisticTaskUpdate = (agentId: string, ctx: TaskMutationContext | undefined): boolean => {
  if (!ctx?.prev || getTaskSyncVersion(agentId) !== ctx.syncVersion) {
    return false;
  }
  queryClient.setQueryData(taskQueryKey(agentId), ctx.prev);
  return true;
};

type MarkReadVars = { workspaceId: string; agentId: string };

/** Optimistically mark an agent as read. */
export const useMarkReadMutation = (): UseMutationResult<unknown, Error, MarkReadVars, TaskMutationContext> =>
  useMutation({
    mutationFn: (vars: MarkReadVars) =>
      markWorkspaceAgentRead({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } }),
    onMutate: (vars): TaskMutationContext =>
      applyOptimisticTaskUpdate(vars.agentId, (prev) => ({ ...prev, lastReadAt: new Date().toISOString() })),
    onError: (_e, vars, ctx): void => {
      rollbackOptimisticTaskUpdate(vars.agentId, ctx);
    },
  });

type MarkUnreadVars = { workspaceId: string; agentId: string };

/**
 * Optimistically mark an agent as unread, recording the unread override that
 * keeps the auto mark-read (`useMarkRead`) from immediately undoing it. A
 * task the stream hasn't delivered is a no-op — nothing to flip, nothing to
 * persist. Rollback clears the override along with the value: the persist
 * failed, so auto mark-read should resume.
 */
export const useMarkUnreadMutation = (): UseMutationResult<unknown, Error, MarkUnreadVars, TaskMutationContext> =>
  useMutation({
    mutationFn: (vars: MarkUnreadVars) => {
      if (!queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId))) {
        return Promise.resolve(undefined);
      }
      return markWorkspaceAgentUnread({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } });
    },
    onMutate: (vars): TaskMutationContext =>
      applyOptimisticTaskUpdate(vars.agentId, (prev) => {
        // Recorded against the pre-flip task so the override's lifetime is
        // keyed to the task's state at mark time (see unreadOverrides.ts).
        setUnreadOverride(vars.agentId, prev);
        return { ...prev, lastReadAt: null };
      }),
    onError: (_e, vars, ctx): void => {
      if (rollbackOptimisticTaskUpdate(vars.agentId, ctx)) {
        clearUnreadOverride(vars.agentId);
      }
    },
  });

type RenameVars = { agentId: string; newTitle: string };

/** Optimistically rename an agent. */
export const useTaskRenameMutation = (
  workspaceId: string,
): UseMutationResult<unknown, Error, RenameVars, TaskMutationContext> =>
  useMutation({
    mutationFn: (vars: RenameVars) =>
      renameWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: vars.agentId },
        body: { title: vars.newTitle },
      }),
    onMutate: (vars): TaskMutationContext =>
      applyOptimisticTaskUpdate(vars.agentId, (prev) => ({ ...prev, title: vars.newTitle })),
    onError: (_e, vars, ctx): void => {
      rollbackOptimisticTaskUpdate(vars.agentId, ctx);
    },
  });

type RestoreVars = { workspaceId: string; agentId: string };

/**
 * Restore a soft-deleted agent. No optimistic write: the client holds only a
 * `null` tombstone, so there is nothing to show until the WS delivers the
 * restored task — and consequently nothing to roll back on failure.
 */
export const useRestoreTaskMutation = (): UseMutationResult<unknown, Error, RestoreVars, unknown> =>
  useMutation({
    mutationFn: (vars: RestoreVars) =>
      restoreWorkspaceAgent({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } }),
  });
