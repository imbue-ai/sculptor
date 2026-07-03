import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { markWorkspaceAgentRead } from "../../../api";
import { taskAtomFamily } from "../atoms/tasks";
import { clearUnreadOverride, isUnreadOverrideActive } from "../atoms/unreadOverrides";

const DEBOUNCE_MS = 1000;

export const useMarkRead = (workspaceID: string, agentID: string): void => {
  const task = useAtomValue(taskAtomFamily(agentID));
  const setTask = useSetAtom(taskAtomFamily(agentID));
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Read inside the debounced setTimeout to see the latest state — the captured
  // `task` closure may be stale by the time the timer fires.
  const taskRef = useRef(task);
  taskRef.current = task;

  const markRead = (): void => {
    // Functional update: read the latest atom value at apply time so a stale
    // closure can't clobber unrelated task fields that changed since render.
    setTask((prev) => (prev ? { ...prev, lastReadAt: new Date().toISOString() } : prev));
    markWorkspaceAgentRead({ path: { workspace_id: workspaceID, agent_id: agentID } }).catch(() => {
      // Fire-and-forget: the server-authoritative value will arrive via WebSocket
    });
  };

  // Mark as read on mount / agent change. This is the "fresh activation" of the
  // agent, so it also ends any explicit "Mark as unread" (see unreadOverrides.ts):
  // the user coming back to the agent has seen it again.
  useEffect(() => {
    if (!task) {
      return;
    }
    clearUnreadOverride(agentID);
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
      // Skip while the user's explicit "Mark as unread" is still active — don't
      // undo their action. The override holds through the update that scheduled
      // this timer when the user marked the agent unread after it, and through
      // every streaming tick (including the completion) of a run the agent was
      // marked unread during. Once the override expires — the next agent turn
      // after the mark, or after the marked run completes — the normal auto
      // mark-read resumes for the agent being viewed.
      const latest = taskRef.current;
      if (latest && isUnreadOverrideActive(agentID, latest)) {
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
