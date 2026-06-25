import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useRef } from "react";

import { markWorkspaceAgentRead } from "../../../api";
import { taskAtomFamily } from "../atoms/tasks";

const DEBOUNCE_MS = 1000;

export const useMarkRead = (workspaceID: string, agentID: string): void => {
  const task = useAtomValue(taskAtomFamily(agentID));
  const setTask = useSetAtom(taskAtomFamily(agentID));
  const store = useStore();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True while a debounced mark-read is scheduled but hasn't fired yet, so the
  // cleanup below can flush it when the user leaves this agent.
  const hasPendingReadRef = useRef(false);

  const markRead = (): void => {
    // Functional update: read the latest atom value at apply time so a stale
    // closure can't clobber unrelated task fields that changed since render.
    setTask((prev) => (prev ? { ...prev, lastReadAt: new Date().toISOString() } : prev));
    markWorkspaceAgentRead({ path: { workspace_id: workspaceID, agent_id: agentID } }).catch(() => {
      // Fire-and-forget: the server-authoritative value will arrive via WebSocket
    });
  };

  // Whether the user has explicitly marked THIS agent unread (lastReadAt=null).
  // Read from the store, not the rendered `task`: on an agent switch the hook
  // re-renders to the new agent before the departing agent's cleanup runs, so a
  // render-scoped value would be the wrong agent; the cleanup's `agentID` closure
  // still points at the departing one.
  const isExplicitlyUnread = (): boolean => store.get(taskAtomFamily(agentID))?.lastReadAt === null;

  // Mark as read on mount / agent change, and flush a still-pending debounced
  // read when leaving this agent so it persists as read before the route changes.
  useEffect(() => {
    if (task) {
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
      // Skip if the user explicitly marked unread while the timer was pending —
      // don't undo their action.
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
