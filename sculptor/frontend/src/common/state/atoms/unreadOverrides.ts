// Explicit per-agent "Mark as unread" overrides.
//
// Marking an agent unread (markAgentUnreadAtom) does three things:
//   1. records an override for the task, keyed to the task's CURRENT updatedAt;
//   2. optimistically clears the task's lastReadAt so every dot derivation
//      (panel tab, workspace row) flips to unread immediately;
//   3. persists the state through the mark-unread endpoint (the server clears
//      last_read_at; its authoritative view arrives back over WebSocket).
//
// The override exists on top of the persisted lastReadAt=null because of how the
// auto mark-read loop (useMarkRead) behaves: while the user is VIEWING an agent,
// useMarkRead re-marks it read whenever the task updates. The override tells that
// loop "the user explicitly wants this agent unread — leave it alone", and it keeps
// the dot unread even if a stale WebSocket frame briefly restores a non-null
// lastReadAt before the mark-unread round-trip lands.
//
// Override lifetime (transient, in-memory — the durable unread state is the
// server's cleared last_read_at, which survives reloads on its own):
//   - SET when the user picks "Mark as unread" for an agent.
//   - ACTIVE only while the task's updatedAt still equals the value recorded at
//     mark time. A new agent turn (updatedAt advancing) expires it: if the user is
//     viewing the agent the auto mark-read resumes with the new content, and if
//     they are not, the ordinary lastReadAt/updatedAt comparison keeps the dot
//     unread on its own.
//   - CLEARED on a fresh activation of the agent — the viewed agent changing TO
//     this agent (switching tabs or workspaces back onto it), tracked by
//     useMarkRead's agent key — at which point useMarkRead marks it read again.
//     Re-clicking the tab of the agent that is already being viewed is not a
//     fresh activation and leaves the override alone.
//   - Also DROPPED when the agent's panel is evicted from the registry (the agent
//     was deleted, or its workspace was left). Both are safe: the persisted
//     lastReadAt=null keeps the dot unread on its own, and returning to the agent
//     is a fresh activation that would clear the override anyway.

import { atom } from "jotai";

import { markWorkspaceAgentUnread } from "../../../api";
import { taskAtomFamily } from "./tasks";

// taskId → the task's updatedAt at the moment the user marked it unread. A plain
// module-level map (not an atom) so the pure registry derivation
// (deriveDynamicPanels) and useMarkRead's debounce timer can consult it
// synchronously; every observable transition (set / expiry / clear) coincides
// with a task-atom write that already re-runs the dot derivations.
const overriddenUpdatedAtByTaskId = new Map<string, string>();

export function setUnreadOverride(taskId: string, updatedAt: string): void {
  overriddenUpdatedAtByTaskId.set(taskId, updatedAt);
}

// Active only while the task's updatedAt still matches the recorded value — a new
// agent turn expires the override without an explicit clear.
export function isUnreadOverrideActive(taskId: string, currentUpdatedAt: string): boolean {
  return overriddenUpdatedAtByTaskId.get(taskId) === currentUpdatedAt;
}

export function clearUnreadOverride(taskId: string): void {
  overriddenUpdatedAtByTaskId.delete(taskId);
}

export function resetUnreadOverridesForTesting(): void {
  overriddenUpdatedAtByTaskId.clear();
}

// The user-facing "Mark as unread" action: record the override, flip the task's
// lastReadAt optimistically so the dot updates immediately, and persist.
export const markAgentUnreadAtom = atom(null, (get, set, target: { workspaceId: string; taskId: string }): void => {
  const task = get(taskAtomFamily(target.taskId));
  if (task === null) {
    return;
  }
  setUnreadOverride(target.taskId, task.updatedAt);
  set(taskAtomFamily(target.taskId), { ...task, lastReadAt: null });
  markWorkspaceAgentUnread({ path: { workspace_id: target.workspaceId, agent_id: target.taskId } }).catch(() => {
    // Fire-and-forget: the server-authoritative value will arrive via WebSocket.
  });
});
