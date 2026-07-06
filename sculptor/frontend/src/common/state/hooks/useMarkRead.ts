/**
 * Auto mark-read hook: marks the viewed agent as read on activation and
 * debounced re-reads on `updatedAt` changes. The optimistic-update/rollback
 * logic is owned by `useMarkReadMutation`; this hook orchestrates the timing
 * (debounce, explicit-unread-override guard, flush-on-leave).
 *
 * Reads `task` from Jotai atoms for synchronous reactivity (needed for the
 * debounce timer logic and cleanup flush). During the Phase 2 → Phase 3
 * migration the WS bridge dual-writes both caches, so Jotai reads stay correct
 * while mutations go through `useMutation`. The `isExplicitlyUnread()` guard
 * reads the TanStack Query cache (snapshot, not subscribed) — this is fine
 * because it's only consulted in callbacks, not in render.
 *
 * Flush-on-leave (the cleanup path that fires when a user navigates away
 * mid-debounce) uses a direct API call + dual-write instead of the mutation
 * hook, because TanStack Query cancels pending `mutate()` invocations on
 * hook unmount. The dual-write is idempotent: the WS stream is the
 * authoritative source and will overwrite the optimistic write on the next
 * frame.
 */

import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useRef } from "react";

import { markWorkspaceAgentRead } from "../../../api";
import { queryClient, taskQueryKey } from "../../queryClient.ts";
import { taskAtomFamily } from "../atoms/tasks";
import { clearUnreadOverride, isUnreadOverrideActive } from "../atoms/unreadOverrides";
import { useMarkReadMutation } from "../mutations";

const DEBOUNCE_MS = 1000;

export const useMarkRead = (workspaceID: string, agentID: string): void => {
  const task = useAtomValue(taskAtomFamily(agentID));
  const setTask = useSetAtom(taskAtomFamily(agentID));
  const store = useStore();
  const { mutate: markReadMutate } = useMarkReadMutation(workspaceID, agentID);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True while a debounced mark-read is scheduled but hasn't fired yet, so the
  // cleanup below can flush it when the user leaves this agent.
  const hasPendingReadRef = useRef(false);

  /** Optimistic mark-read via the mutation hook (handles rollback on failure). */
  const markRead = (): void => {
    markReadMutate();
  };

  /**
   * Direct mark-read used in the flush-on-leave cleanup path. Bypasses the
   * mutation hook because `.mutate()` is a no-op on an unmounted hook; TanStack
   * Query cancels pending invocations when the observer that owns them
   * disposes. Dual-writes Jotai + TanStack Query cache so both stay in sync
   * until the WS stream delivers the authoritative value.
   */
  const markReadForFlush = (): void => {
    const now = new Date().toISOString();
    setTask((prev) => (prev ? { ...prev, lastReadAt: now } : prev));
    const prev = queryClient.getQueryData(taskQueryKey(agentID));
    if (prev) {
      queryClient.setQueryData(taskQueryKey(agentID), { ...prev, lastReadAt: now });
    }
    markWorkspaceAgentRead({ path: { workspace_id: workspaceID, agent_id: agentID } }).catch((error) => {
      // Fire-and-forget: the server-authoritative value will arrive via WebSocket.
      console.warn("Failed to persist mark-read; the server value will arrive via WebSocket.", error);
    });
  };

  // Whether the user's explicit "Mark as unread" is still in force for THIS agent
  // (see unreadOverrides.ts for the override's lifetime). Read the task from the
  // store, not the rendered `task`: on an agent switch the hook re-renders to the
  // new agent before the departing agent's cleanup runs, so a render-scoped value
  // would be the wrong agent; the cleanup's `agentID` closure still points at the
  // departing one.
  const isExplicitlyUnread = (): boolean => {
    const latest = store.get(taskAtomFamily(agentID));
    return latest !== null && isUnreadOverrideActive(agentID, latest);
  };

  // Mark as read on mount / agent change, and flush a still-pending debounced
  // read when leaving this agent so it persists as read before the view moves on.
  // A fresh activation is the user seeing the agent again, so it also ends any
  // explicit "Mark as unread" (see unreadOverrides.ts).
  useEffect(() => {
    if (task) {
      clearUnreadOverride(agentID);
      markRead();
    }

    return (): void => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      if (hasPendingReadRef.current) {
        hasPendingReadRef.current = false;
        // Don't undo an explicit mark-unread the user performed while the timer
        // was pending.
        if (!isExplicitlyUnread()) {
          markReadForFlush();
        }
      }
    };
    // Only run on mount and when agentID changes, not on every task update
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentID]);

  // Re-fire (debounced) when updatedAt changes while the hook is active
  const updatedAt = task?.updatedAt;
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }

    if (!task || !updatedAt) {
      return;
    }

    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    hasPendingReadRef.current = true;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      hasPendingReadRef.current = false;
      // Skip while the user's explicit "Mark as unread" is still active — don't
      // undo their action. The override holds through the update that scheduled
      // this timer when the user marked the agent unread after it, and through
      // every streaming tick (including the completion) of a run the agent was
      // marked unread during. Once the override expires — the next agent turn
      // after the mark, or after the marked run completes — the normal auto
      // mark-read resumes for the agent being viewed.
      if (isExplicitlyUnread()) {
        return;
      }
      markRead();
    }, DEBOUNCE_MS);

    return (): void => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [updatedAt]);
};
