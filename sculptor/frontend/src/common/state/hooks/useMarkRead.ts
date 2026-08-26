/**
 * Auto mark-read: marks the viewed agent read on activation and schedules
 * debounced re-reads on `updatedAt` changes. The optimistic-update/rollback
 * logic lives in `useMarkReadMutation`; this hook only decides *when* to fire
 * it — including flushing a still-pending debounced read when the user leaves
 * the agent. Firing the mutation from the unmount cleanup is safe: mutations
 * run to completion after unmount (only mutate-time callbacks are dropped,
 * and none are used here).
 */

import { useEffect, useRef } from "react";

import type { CodingAgentTaskView } from "../../../api";
import { queryClient, taskQueryKey } from "../../queryClient.ts";
import { clearUnreadOverride, isUnreadOverrideActive } from "../atoms/unreadOverrides";
import { useMarkReadMutation } from "../mutations";
import { useTask } from "./useTask";

const DEBOUNCE_MS = 1000;

export const useMarkRead = (workspaceID: string, agentID: string): void => {
  const task = useTask(agentID);
  const { mutate: markReadMutate } = useMarkReadMutation();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True while a debounced mark-read is scheduled but hasn't fired yet, so the
  // cleanup below can flush it when the user leaves this agent.
  const hasPendingReadRef = useRef(false);

  // The ids are bound as mutation variables at call time, so the cleanup's
  // closure marks the *departing* agent even though the hook has already
  // re-rendered for the next one by the time the cleanup runs.
  const markRead = (): void => {
    markReadMutate({ workspaceId: workspaceID, agentId: agentID });
  };

  // Read the latest task from the cache (not the rendered `task`): the
  // decision must reflect updates that arrived after this closure was created.
  const isExplicitlyUnread = (): boolean => {
    const latest = queryClient.getQueryData<CodingAgentTaskView | null>(taskQueryKey(agentID));
    return !!latest && isUnreadOverrideActive(agentID, latest);
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
          markRead();
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
