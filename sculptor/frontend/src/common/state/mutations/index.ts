/**
 * TanStack Query mutation hooks for agent-task operations.
 *
 * Each hook returns a `useMutation` result (or a thin wrapper exposing
 * `execute`). The `onMutate` callback snapshots the current cache entry and
 * applies the optimistic update; `onError` restores the snapshot so the UI
 * doesn't silently diverge from the server when a POST fails. The server-
 * authoritative value always arrives via the WebSocket stream
 * (`syncTasksToQueryCache` in `useUnifiedStream`), so `onSuccess` never writes
 * the cache — it handles UI side-effects only (analytics, toast dismissal).
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { useSetAtom, useStore } from "jotai";
import { useLayoutEffect, useRef } from "react";

import type { CodingAgentTaskView } from "../../../api";
import {
  deleteWorkspaceAgent,
  markWorkspaceAgentRead,
  markWorkspaceAgentUnread,
  renameWorkspaceAgent,
  restoreWorkspaceAgent,
} from "../../../api";
import { ToastType } from "../../../components/Toast.tsx";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX, taskIdsQueryKey, taskQueryKey } from "../../queryClient.ts";
import { deleteErrorToastAtom } from "../atoms/toasts";
import { setUnreadOverride } from "../atoms/unreadOverrides";
import { agentIdForWorkspaceAtomFamily, setAgentForWorkspaceAtom } from "../atoms/workspaces.ts";

/** Rollback context captured by every `onMutate` callback. */
type TaskMutationContext = { prev: CodingAgentTaskView | null | undefined };

// ─────────────────────────────────────────────────────────────
// Mark-read
// ─────────────────────────────────────────────────────────────

/**
 * Optimistically mark an agent as read. The timestamp applied locally is a
 * close approximation; the server-authoritative value (which may differ by a
 * few ms) arrives via the WS stream and overwrites it.
 */
export const useMarkReadMutation = (
  workspaceId: string,
  agentId: string,
): UseMutationResult<unknown, Error, void, TaskMutationContext> =>
  useMutation({
    mutationFn: () => markWorkspaceAgentRead({ path: { workspace_id: workspaceId, agent_id: agentId } }),
    onMutate: async (): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(agentId));
      if (prev) {
        queryClient.setQueryData(taskQueryKey(agentId), {
          ...prev,
          lastReadAt: new Date().toISOString(),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(agentId), ctx.prev);
      }
    },
  });

// ─────────────────────────────────────────────────────────────
// Mark-unread
// ─────────────────────────────────────────────────────────────

/**
 * Optimistically mark an agent as unread. Records an unread override (see
 * `unreadOverrides.ts`) so `useMarkRead`'s auto mark-read loop leaves the
 * dot alone until the user explicitly switches agents or the next turn lands.
 */
export const useMarkUnreadMutation = (
  workspaceId: string,
  agentId: string,
): UseMutationResult<unknown, Error, void, TaskMutationContext> =>
  useMutation({
    mutationFn: () => markWorkspaceAgentUnread({ path: { workspace_id: workspaceId, agent_id: agentId } }),
    onMutate: async (): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(agentId));
      if (prev) {
        setUnreadOverride(agentId, prev);
        queryClient.setQueryData(taskQueryKey(agentId), { ...prev, lastReadAt: null });
      }
      return { prev };
    },
    onError: (_e, _v, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(agentId), ctx.prev);
      }
    },
  });

// ─────────────────────────────────────────────────────────────
// Rename
// ─────────────────────────────────────────────────────────────

/**
 * Optimistically rename an agent by `newTitle`. The server-authoritative task
 * arrives via WS; on failure the previous cache entry is restored.
 */
type RenameVars = { agentId: string; newTitle: string };

export const useTaskRenameMutation = (
  workspaceId: string,
): UseMutationResult<unknown, Error, RenameVars, TaskMutationContext> =>
  useMutation({
    mutationFn: (vars: RenameVars) =>
      renameWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: vars.agentId },
        body: { title: vars.newTitle },
      }),
    onMutate: async (vars): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId));
      if (prev) {
        queryClient.setQueryData(taskQueryKey(vars.agentId), { ...prev, title: vars.newTitle });
      }
      return { prev };
    },
    onError: (_e, vars, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(vars.agentId), ctx.prev);
      }
    },
  });

// ─────────────────────────────────────────────────────────────
// Delete (soft)
// ─────────────────────────────────────────────────────────────

type DeleteVars = { taskId: string; taskTitle: string };

/**
 * Optimistically soft-delete an agent. Navigation and analytics side-effects
 * are delegated to the caller; this hook handles cache rollback on failure
 * and surfaces a retry-able error toast via the shared `deleteErrorToastAtom`.
 *
 * `onNavigateAfterDelete` fires in `onMutate` *before* the API call, giving
 * consumers a window where the tab is already removed from the UI but the
 * mutation hasn't completed — matching the legacy optimistic-delete UX.
 */
export const useOptimisticTaskDeleteMutation = (
  workspaceId: string,
  options: {
    onNavigateAfterDelete?: (taskId: string, deletedTask: CodingAgentTaskView) => void;
  } = {},
): UseMutationResult<unknown, Error, DeleteVars, TaskMutationContext | undefined> => {
  const store = useStore();
  const setDeleteErrorToast = useSetAtom(deleteErrorToastAtom);

  // onNavigateAfterDelete may change each render; keep it reachable from
  // useMutation's stable onMutate closure through a ref.
  const onNavigateAfterDeleteRef = useRef(options.onNavigateAfterDelete);
  useLayoutEffect((): void => {
    onNavigateAfterDeleteRef.current = options.onNavigateAfterDelete;
  }, [options.onNavigateAfterDelete]);

  const mutation = useMutation({
    mutationKey: [SCULPTOR_QUERY_KEY_PREFIX, "deleteTask"],
    mutationFn: (vars: DeleteVars) =>
      deleteWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: vars.taskId },
        meta: { skipWsAck: true },
      }),
    onMutate: async (vars): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.taskId));
      if (!prev) {
        return { prev };
      }

      // Optimistic: remove from cache and task-ids list.
      queryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.taskId), null);
      const currentIds = queryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey()) ?? [];
      queryClient.setQueryData<ReadonlyArray<string>>(
        taskIdsQueryKey(),
        currentIds.filter((id) => id !== vars.taskId),
      );

      // Dismiss this task as the workspace's saved agent so cold-start redirects
      // don't target the deleted route.
      if (store.get(agentIdForWorkspaceAtomFamily(workspaceId)) === vars.taskId) {
        store.set(setAgentForWorkspaceAtom, { wsId: workspaceId, agentId: null });
      }

      onNavigateAfterDeleteRef.current?.(vars.taskId, prev);

      return { prev };
    },
    onError: (_e, vars, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined && ctx.prev !== null) {
        queryClient.setQueryData(taskQueryKey(vars.taskId), ctx.prev);
        const currentIds = queryClient.getQueryData<ReadonlyArray<string>>(taskIdsQueryKey()) ?? [];
        if (!currentIds.includes(vars.taskId)) {
          queryClient.setQueryData(taskIdsQueryKey(), [...currentIds, vars.taskId]);
        }
      }

      setDeleteErrorToast({
        title: `Failed to delete "${vars.taskTitle}"`,
        description: "The agent has been restored. Try again or check your connection.",
        type: ToastType.ERROR_PROMINENT,
        action: {
          label: "Retry",
          handleClick: (): void => {
            setDeleteErrorToast(null);
            mutate(vars);
          },
        },
      });
    },
  });

  const { mutate } = mutation;
  return mutation;
};

// ─────────────────────────────────────────────────────────────
// Restore
// ─────────────────────────────────────────────────────────────

/**
 * Optimistically restore a soft-deleted agent. Re-adds the task to the cache
 * and the task-ids list; on failure rolls back to the previous (null) state.
 */
type RestoreVars = { agentId: string };

export const useRestoreTaskMutation = (
  workspaceId: string,
): UseMutationResult<unknown, Error, RestoreVars, TaskMutationContext> =>
  useMutation({
    mutationFn: (vars: { agentId: string }) =>
      restoreWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: vars.agentId },
      }),
    onMutate: async (vars): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId));
      // Optimistically clear the "deleted" state. The WS bridge will write the
      // full restored task shortly.
      queryClient.setQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId), null);
      return { prev };
    },
    onError: (_e, vars, ctx: TaskMutationContext | undefined): void => {
      // Rollback: restore the pre-mutation cache state (null for a soft-deleted task).
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(vars.agentId), ctx.prev);
      }
    },
  });
