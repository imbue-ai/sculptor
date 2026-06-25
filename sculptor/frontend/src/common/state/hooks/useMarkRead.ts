import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { markWorkspaceAgentRead } from "../../../api";
import { taskAtomFamily } from "../atoms/tasks";

const DEBOUNCE_MS = 1000;

export const useMarkRead = (workspaceID: string, agentID: string): void => {
  const task = useAtomValue(taskAtomFamily(agentID));
  const setTask = useSetAtom(taskAtomFamily(agentID));
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Read inside the debounced setTimeout to see the latest state — the captured
  // `task` closure may be stale by the time the timer fires.
  const taskRef = useRef(task);
  // Keep the ref current after every commit so the pending timer reads the latest task.
  useEffect(() => {
    taskRef.current = task;
  });

  const markRead = (): void => {
    // Functional update: read the latest atom value at apply time so a stale
    // closure can't clobber unrelated task fields that changed since render.
    setTask((prev) => (prev ? { ...prev, lastReadAt: new Date().toISOString() } : prev));
    markWorkspaceAgentRead({ path: { workspace_id: workspaceID, agent_id: agentID } }).catch(() => {
      // Fire-and-forget: the server-authoritative value will arrive via WebSocket
    });
  };

  // Mark as read on mount
  useEffect(() => {
    if (!task) {
      return;
    }
    markRead();
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
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      // Skip if the user explicitly marked unread (lastReadAt=null) while the
      // timer was pending — don't undo their action.
      if (taskRef.current?.lastReadAt === null) {
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
