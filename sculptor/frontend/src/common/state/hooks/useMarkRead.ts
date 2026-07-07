/**
 * Auto mark-read: marks the viewed agent read on activation and schedules
 * debounced re-reads on `updatedAt` changes. The optimistic-update/rollback
 * logic lives in `useMarkReadMutation`; this hook handles the timing.
 *
 * Flush-on-leave uses a direct API call + cache write instead of the mutation
 * hook, because TanStack Query cancels pending `mutate()` on hook unmount.
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

  const markRead = (): void => {
    markReadMutate();
  };

  /** Direct mark-read for the flush-on-leave path (bypasses the mutation hook). */
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

  // Read from the store (not the rendered `task`): on an agent switch the
  // cleanup runs after the hook has already re-rendered for the new agent,
  // so a render-scoped value would be the wrong agent.
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
      // Skip while the user's explicit "Mark as unread" override is active.
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
