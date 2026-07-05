import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useEffect, useRef } from "react";

import { markWorkspaceAgentRead } from "../../../api";
import { agentAtomFamily } from "../atoms/agents";
import { clearUnreadOverride, isUnreadOverrideActive } from "../atoms/unreadOverrides";

const DEBOUNCE_MS = 1000;

export const useMarkRead = (workspaceID: string, agentID: string): void => {
  const agent = useAtomValue(agentAtomFamily(agentID));
  const setAgent = useSetAtom(agentAtomFamily(agentID));
  const store = useStore();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True while a debounced mark-read is scheduled but hasn't fired yet, so the
  // cleanup below can flush it when the user leaves this agent.
  const hasPendingReadRef = useRef(false);

  const markRead = (): void => {
    // Functional update: read the latest atom value at apply time so a stale
    // closure can't clobber unrelated agent fields that changed since render.
    setAgent((prev) => (prev ? { ...prev, lastReadAt: new Date().toISOString() } : prev));
    markWorkspaceAgentRead({ path: { workspace_id: workspaceID, agent_id: agentID } }).catch(() => {
      // Fire-and-forget: the server-authoritative value will arrive via WebSocket
    });
  };

  // Whether the user's explicit "Mark as unread" is still in force for THIS agent
  // (see unreadOverrides.ts for the override's lifetime). Read the agent from the
  // store, not the rendered `agent`: on an agent switch the hook re-renders to the
  // new agent before the departing agent's cleanup runs, so a render-scoped value
  // would be the wrong agent; the cleanup's `agentID` closure still points at the
  // departing one.
  const isExplicitlyUnread = (): boolean => {
    const latest = store.get(agentAtomFamily(agentID));
    return latest !== null && isUnreadOverrideActive(agentID, latest);
  };

  // Mark as read on mount / agent change, and flush a still-pending debounced
  // read when leaving this agent so it persists as read before the view moves on.
  // A fresh activation is the user seeing the agent again, so it also ends any
  // explicit "Mark as unread" (see unreadOverrides.ts).
  useEffect(() => {
    if (agent) {
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
    // Only run on mount and when agentID changes, not on every agent update
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentID]);

  // Re-fire (debounced) when updatedAt changes while the hook is active
  const updatedAt = agent?.updatedAt;
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }

    if (!agent || !updatedAt) {
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
