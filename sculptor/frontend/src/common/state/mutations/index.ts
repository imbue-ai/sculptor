/**
 * TanStack Query mutation hooks for agent operations.
 *
 * The query cache is the single written store for agent state: the WS bridge
 * writes authoritative frames, these hooks write optimistic updates, and
 * `useAgentQueryMirror` projects the cache into the legacy Jotai atoms — so no
 * hook here touches Jotai.
 *
 * Optimistic pattern: `onMutate` snapshots the cache entry plus the agent's
 * WS sync-version; `onError` restores the snapshot only if the version is
 * unchanged. If a WS frame wrote the agent while the request was in flight,
 * the frame holds server truth (whether or not the mutation committed) and
 * the stale snapshot must lose. `onSuccess` never writes: a successful
 * mutation changes the agent server-side, so the delta stream delivers the
 * authoritative value.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import type { CodingAgentTaskView } from "../../../api";
import {
  deleteWorkspaceAgent,
  markWorkspaceAgentRead,
  markWorkspaceAgentUnread,
  renameWorkspaceAgent,
  restoreWorkspaceAgent,
} from "../../../api";
import { HTTPException } from "../../utils/errors.ts";
import { clearUnreadOverride, setUnreadOverride } from "../atoms/unreadOverrides";
import { agentIdsQueryKey, agentQueryKey, getAgentSyncVersion, queryClient } from "../queryClient.ts";

/**
 * Settle deadline for optimistic state mutations, passed as `meta.timeout`
 * (which gives the request an AbortSignal — without it a request to a wedged
 * backend never settles, so the rollback/toast failure path is unreachable
 * and the optimistic value sticks on screen forever, SCU-1833).
 *
 * Must exceed the backend's 15s SQLite writer-lock wait
 * (`_SQLITE_BUSY_TIMEOUT_SEC` in `sculptor/database/core.py`) so writer
 * contention surfaces as the backend's own error response, not a frontend
 * abort racing it.
 */
export const MUTATION_SETTLE_TIMEOUT_MS = 30_000;

export type AgentMutationContext = {
  prev: CodingAgentTaskView | null | undefined;
  syncVersion: number;
};

/** Snapshot the cached agent and, when it exists, replace it with `update(prev)`. */
export const applyOptimisticAgentUpdate = (
  agentId: string,
  update: (prev: CodingAgentTaskView) => CodingAgentTaskView,
): AgentMutationContext => {
  const prev = queryClient.getQueryData<CodingAgentTaskView | null>(agentQueryKey(agentId));
  if (prev) {
    queryClient.setQueryData(agentQueryKey(agentId), update(prev));
  }
  return { prev, syncVersion: getAgentSyncVersion(agentId) };
};

/**
 * Undo an optimistic update after a failed request, unless nothing was
 * written or a WS frame wrote the agent in the meantime. Returns whether the
 * snapshot was restored.
 */
export const rollbackOptimisticAgentUpdate = (agentId: string, ctx: AgentMutationContext | undefined): boolean => {
  if (!ctx?.prev || getAgentSyncVersion(agentId) !== ctx.syncVersion) {
    return false;
  }
  queryClient.setQueryData(agentQueryKey(agentId), ctx.prev);
  return true;
};

/**
 * Snapshot an agent, tombstone it (`null` entry), and drop its id from the ids
 * list. Unlike the entry-only helpers, delete also touches the ids list, so it
 * has its own apply/rollback pair. Exported so the delete hook can apply the
 * tombstone synchronously before its navigation callbacks run — `onMutate` is
 * a microtask behind `.mutate()`, and callbacks read the post-delete store.
 *
 * When the cache never had the agent (or already holds a tombstone), nothing is
 * applied — writing a tombstone for an unknown entry would fake "deleted", and
 * the untouched context keeps the rollback a no-op. The caller still sends the
 * DELETE: the server is the authority on deletability.
 */
export const applyOptimisticAgentDelete = (agentId: string): AgentMutationContext => {
  const prev = queryClient.getQueryData<CodingAgentTaskView | null>(agentQueryKey(agentId));
  const context = { prev, syncVersion: getAgentSyncVersion(agentId) };
  if (!prev) {
    return context;
  }
  queryClient.setQueryData<CodingAgentTaskView | null>(agentQueryKey(agentId), null);
  const ids = queryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey()) ?? [];
  queryClient.setQueryData<ReadonlyArray<string>>(
    agentIdsQueryKey(),
    ids.filter((id) => id !== agentId),
  );
  return context;
};

/**
 * Undo an optimistic delete after a failed request: restore the snapshot and
 * re-append the id, unless a WS frame wrote the agent while the request was in
 * flight (the frame holds server truth and must win). Symmetric with
 * `applyOptimisticAgentDelete` — restores both the entry and the ids list.
 */
export const rollbackOptimisticAgentDelete = (agentId: string, ctx: AgentMutationContext | undefined): void => {
  if (!ctx?.prev || getAgentSyncVersion(agentId) !== ctx.syncVersion) {
    return;
  }
  queryClient.setQueryData(agentQueryKey(agentId), ctx.prev);
  const ids = queryClient.getQueryData<ReadonlyArray<string>>(agentIdsQueryKey()) ?? [];
  if (!ids.includes(agentId)) {
    queryClient.setQueryData<ReadonlyArray<string>>(agentIdsQueryKey(), [...ids, agentId]);
  }
};

type MarkReadVars = { workspaceId: string; agentId: string };

/** Optimistically mark an agent as read. */
export const useMarkReadMutation = (): UseMutationResult<unknown, Error, MarkReadVars, AgentMutationContext> =>
  useMutation({
    mutationFn: (vars: MarkReadVars) =>
      markWorkspaceAgentRead({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } }),
    onMutate: (vars): AgentMutationContext =>
      applyOptimisticAgentUpdate(vars.agentId, (prev) => ({ ...prev, lastReadAt: new Date().toISOString() })),
    onError: (_e, vars, ctx): void => {
      rollbackOptimisticAgentUpdate(vars.agentId, ctx);
    },
  });

type MarkUnreadVars = { workspaceId: string; agentId: string };

/**
 * Optimistically mark an agent as unread, recording the unread override that
 * keeps the auto mark-read (`useMarkRead`) from immediately undoing it. An
 * agent the stream hasn't delivered is a no-op — nothing to flip, nothing to
 * persist. Rollback clears the override along with the value: the persist
 * failed, so auto mark-read should resume.
 */
export const useMarkUnreadMutation = (): UseMutationResult<unknown, Error, MarkUnreadVars, AgentMutationContext> =>
  useMutation({
    mutationFn: (vars: MarkUnreadVars) => {
      if (!queryClient.getQueryData<CodingAgentTaskView | null>(agentQueryKey(vars.agentId))) {
        return Promise.resolve(undefined);
      }
      return markWorkspaceAgentUnread({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } });
    },
    onMutate: (vars): AgentMutationContext =>
      applyOptimisticAgentUpdate(vars.agentId, (prev) => {
        // Recorded against the pre-flip agent so the override's lifetime is
        // keyed to the agent's state at mark time (see unreadOverrides.ts).
        setUnreadOverride(vars.agentId, prev);
        return { ...prev, lastReadAt: null };
      }),
    onError: (_e, vars, ctx): void => {
      if (rollbackOptimisticAgentUpdate(vars.agentId, ctx)) {
        clearUnreadOverride(vars.agentId);
      }
    },
  });

type RenameVars = { agentId: string; newTitle: string };

/** Optimistically rename an agent. */
export const useAgentRenameMutation = (
  workspaceId: string,
): UseMutationResult<unknown, Error, RenameVars, AgentMutationContext> =>
  useMutation({
    mutationFn: (vars: RenameVars) =>
      renameWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: vars.agentId },
        body: { title: vars.newTitle },
      }),
    onMutate: (vars): AgentMutationContext =>
      applyOptimisticAgentUpdate(vars.agentId, (prev) => ({ ...prev, title: vars.newTitle })),
    onError: (_e, vars, ctx): void => {
      rollbackOptimisticAgentUpdate(vars.agentId, ctx);
    },
  });

type RestoreVars = { workspaceId: string; agentId: string };

/**
 * Restore a soft-deleted agent. No optimistic write: the client holds only a
 * `null` tombstone, so there is nothing to show until the WS delivers the
 * restored agent — and consequently nothing to roll back on failure.
 */
export const useRestoreAgentMutation = (): UseMutationResult<unknown, Error, RestoreVars, unknown> =>
  useMutation({
    mutationFn: (vars: RestoreVars) =>
      restoreWorkspaceAgent({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } }),
  });

type DeleteVars = {
  workspaceId: string;
  agentId: string;
  // The tombstone is applied by the caller (synchronously, before its
  // navigation callbacks) via `applyOptimisticAgentDelete`, and its snapshot is
  // threaded here so `onError` can roll back. Applying in `onMutate` would land
  // a microtask after `.mutate()`, too late for the callbacks — so this
  // mutation deliberately has no `onMutate`.
  deleteContext: AgentMutationContext;
};

/**
 * Delete an agent. The optimistic tombstone lives in the caller (see
 * `deleteContext`); this hook owns the request and the version-checked
 * rollback. `skipWsAck` lets the request complete without waiting for the WS
 * to acknowledge the removal. Rollback in `onError` (not the caller's `.catch`)
 * so it can't be skipped if the component unmounts mid-request.
 */
export const useDeleteAgentMutation = (): UseMutationResult<unknown, Error, DeleteVars, unknown> =>
  useMutation({
    mutationFn: async (vars: DeleteVars): Promise<void> => {
      try {
        await deleteWorkspaceAgent({
          path: { workspace_id: vars.workspaceId, agent_id: vars.agentId },
          meta: { skipWsAck: true, timeout: MUTATION_SETTLE_TIMEOUT_MS },
        });
      } catch (error) {
        // An already-deleted agent is a success for the user's intent — let
        // the tombstone stand instead of restoring something the server no
        // longer has.
        if (error instanceof HTTPException && error.status === 404) {
          return;
        }
        throw error;
      }
    },
    onError: (_e, vars): void => {
      rollbackOptimisticAgentDelete(vars.agentId, vars.deleteContext);
    },
  });
