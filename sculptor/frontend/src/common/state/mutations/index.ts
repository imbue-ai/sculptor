/**
 * TanStack Query mutation hooks for agent-task operations.
 *
 * Each hook snapshots the cache in `onMutate` and restores it in `onError`.
 * The server-authoritative value arrives via the WS stream, so `onSuccess`
 * never writes the cache.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { useStore } from "jotai";

import type { CodingAgentTaskView } from "../../../api";
import {
  markWorkspaceAgentRead,
  markWorkspaceAgentUnread,
  renameWorkspaceAgent,
  restoreWorkspaceAgent,
} from "../../../api";
import { queryClient, taskQueryKey } from "../../queryClient.ts";
import { taskAtomFamily } from "../atoms/tasks";
import { setUnreadOverride } from "../atoms/unreadOverrides";

type TaskMutationContext = { prev: CodingAgentTaskView | null | undefined };

/** Optimistically mark an agent as read. */
export const useMarkReadMutation = (
  workspaceId: string,
  agentId: string,
): UseMutationResult<unknown, Error, void, TaskMutationContext> => {
  const store = useStore();
  return useMutation({
    mutationFn: () => markWorkspaceAgentRead({ path: { workspace_id: workspaceId, agent_id: agentId } }),
    onMutate: async (): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(agentId));
      const now = new Date().toISOString();
      if (prev) {
        const updated = { ...prev, lastReadAt: now };
        queryClient.setQueryData(taskQueryKey(agentId), updated);
        store.set(taskAtomFamily(agentId), updated);
      }
      return { prev };
    },
    onError: (_e, _v, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(agentId), ctx.prev ?? null);
        store.set(taskAtomFamily(agentId), ctx.prev ?? null);
      }
    },
  });
};

type MarkUnreadVars = { workspaceId: string; agentId: string };

/** Optimistically mark an agent as unread, recording the unread override. */
export const useMarkUnreadMutation = (): UseMutationResult<unknown, Error, MarkUnreadVars, TaskMutationContext> => {
  const store = useStore();
  return useMutation({
    mutationFn: (vars: MarkUnreadVars) =>
      markWorkspaceAgentUnread({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } }),
    onMutate: async (vars): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId));
      if (prev) {
        setUnreadOverride(vars.agentId, prev);
        const updated = { ...prev, lastReadAt: null };
        queryClient.setQueryData(taskQueryKey(vars.agentId), updated);
        store.set(taskAtomFamily(vars.agentId), updated);
      }
      return { prev };
    },
    onError: (_e, vars, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(vars.agentId), ctx.prev ?? null);
        store.set(taskAtomFamily(vars.agentId), ctx.prev ?? null);
      }
    },
  });
};

type RenameVars = { agentId: string; newTitle: string };

/** Optimistically rename an agent. */
export const useTaskRenameMutation = (
  workspaceId: string,
): UseMutationResult<unknown, Error, RenameVars, TaskMutationContext> => {
  const store = useStore();
  return useMutation({
    mutationFn: (vars: RenameVars) =>
      renameWorkspaceAgent({
        path: { workspace_id: workspaceId, agent_id: vars.agentId },
        body: { title: vars.newTitle },
      }),
    onMutate: async (vars): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId));
      if (prev) {
        const updated = { ...prev, title: vars.newTitle };
        queryClient.setQueryData(taskQueryKey(vars.agentId), updated);
        store.set(taskAtomFamily(vars.agentId), updated);
      }
      return { prev };
    },
    onError: (_e, vars, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(vars.agentId), ctx.prev ?? null);
        store.set(taskAtomFamily(vars.agentId), ctx.prev ?? null);
      }
    },
  });
};

type RestoreVars = { workspaceId: string; agentId: string };

/** Optimistically restore a soft-deleted agent. */
export const useRestoreTaskMutation = (): UseMutationResult<unknown, Error, RestoreVars, TaskMutationContext> =>
  useMutation({
    mutationFn: (vars: RestoreVars) =>
      restoreWorkspaceAgent({ path: { workspace_id: vars.workspaceId, agent_id: vars.agentId } }),
    onMutate: async (vars): Promise<TaskMutationContext> => {
      const prev = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(vars.agentId));
      return { prev };
    },
    onError: (_e, vars, ctx: TaskMutationContext | undefined): void => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(taskQueryKey(vars.agentId), ctx.prev ?? null);
      }
    },
  });
