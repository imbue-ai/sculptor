// Explicit per-agent "Mark as unread" overrides.
//
// Marking an agent unread (markAgentUnreadAtom) does three things:
//   1. records an override for the agent;
//   2. optimistically clears the agent's lastReadAt so every dot derivation
//      (panel tab, workspace row) flips to unread immediately;
//   3. persists the state through the mark-unread endpoint (the server clears
//      last_read_at; its authoritative view arrives back over WebSocket).
//
// The override exists on top of the persisted lastReadAt=null because of how the
// auto mark-read loop (useMarkRead) behaves: while the user is VIEWING an agent,
// useMarkRead re-marks it read whenever the agent updates. The override tells that
// loop "the user explicitly wants this agent unread — leave it alone", and it keeps
// the dot unread even if a stale WebSocket frame briefly restores a non-null
// lastReadAt before the mark-unread round-trip lands.
//
// Override lifetime (transient, in-memory — the durable unread state is the
// server's cleared last_read_at, which survives reloads on its own):
//   - SET when the user picks "Mark as unread" for an agent.
//   - An agent marked mid-run (RUNNING/BUILDING) HOLDS the override through the
//     rest of that run: streaming ticks advance updatedAt continuously, and they
//     must not silently undo the user's action. When the run completes, the
//     override re-keys to the run's final updatedAt and behaves like an
//     idle-agent override from there.
//   - For an idle agent (or a marked-mid-run agent whose run has completed), the
//     override is keyed to the agent's updatedAt and EXPIRES when the next agent
//     turn advances it: if the user is viewing the agent the auto mark-read
//     resumes with the new content, and if they are not, the ordinary
//     lastReadAt/updatedAt comparison keeps the dot unread on its own.
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

import { markWorkspaceAgentUnread, TaskStatus } from "../../../api";
import type { AgentDotStatus } from "../../utils/statusDot.ts";
import { getAgentDotStatus } from "../../utils/statusDot.ts";
import { agentAtomFamily } from "./agents";

// The agent fields the override lifecycle depends on. Structurally satisfied by
// both CodingAgentTaskView and the registry's DynamicAgentInput.
type AgentReadState = { status: TaskStatus; updatedAt: string };

// What the override is waiting for before it can expire on its own:
//   - "runCompletion": recorded while the agent was running; holds through every
//     streaming tick, then re-keys to the run's final updatedAt once the run
//     completes (becoming a "nextTurn" override).
//   - "nextTurn": expires as soon as the agent's updatedAt moves past the recorded
//     value (a new agent turn).
type UnreadOverride = { expiresOn: "runCompletion" } | { expiresOn: "nextTurn"; updatedAt: string };

// agentId → the active override. A plain module-level map (not an atom) so the pure
// registry derivation (deriveDynamicPanels) and useMarkRead's debounce timer can
// consult it synchronously; every observable transition (set / expiry / re-key /
// clear) coincides with an agent-atom write that already re-runs the dot derivations.
const overridesByAgentId = new Map<string, UnreadOverride>();

// RUNNING and BUILDING are the two "agent is actively working" states — the same
// pair getAgentDotStatus renders as a running dot.
const isMidRun = (status: TaskStatus): boolean => status === TaskStatus.RUNNING || status === TaskStatus.BUILDING;

export const setUnreadOverride = (agentId: string, agent: AgentReadState): void => {
  overridesByAgentId.set(
    agentId,
    isMidRun(agent.status) ? { expiresOn: "runCompletion" } : { expiresOn: "nextTurn", updatedAt: agent.updatedAt },
  );
};

// Whether the user's explicit "Mark as unread" is still in force for this agent,
// given the agent's current status/updatedAt. Observing a marked-mid-run agent after
// its run finished re-keys the override to the run's final updatedAt, so the next
// turn after completion expires it like any idle-agent override. The re-key
// happens on read because every consumer (dot derivations, the useMarkRead guard)
// re-runs on the agent write that carries the completion, so it is observed
// consistently; the mutation is idempotent for a given agent state.
export const isUnreadOverrideActive = (agentId: string, agent: AgentReadState): boolean => {
  const override = overridesByAgentId.get(agentId);
  if (override === undefined) {
    return false;
  }

  if (override.expiresOn === "runCompletion") {
    if (!isMidRun(agent.status)) {
      overridesByAgentId.set(agentId, { expiresOn: "nextTurn", updatedAt: agent.updatedAt });
    }
    return true;
  }
  return override.updatedAt === agent.updatedAt;
};

export const clearUnreadOverride = (agentId: string): void => {
  overridesByAgentId.delete(agentId);
};

export const resetUnreadOverridesForTesting = (): void => {
  overridesByAgentId.clear();
};

// The dot status for one agent with the unread override applied. An explicit
// "Mark as unread" wins over "read": while the override is active a stale
// lastReadAt (e.g. a WebSocket frame that raced the mark-unread round-trip) must
// not show the agent as read. Activity dots (running/waiting/error) keep
// precedence — the override only affects the read/unread classification.
// Every override-aware dot surface (panel tab, workspace sidebar row) derives
// through this one helper so they cannot drift.
//
// `isFocused` marks the viewed agent (see viewedAgentIdAtom): its content is on
// screen, so the BASE derivation already reads it as "read" instead of flashing
// unread while the debounced mark-read lags. The override flip is applied
// STRICTLY AFTER that — an explicit "Mark as unread" must beat viewed-as-read,
// or marking the agent you are looking at unread would silently not stick.
export const getAgentDotStatusWithUnreadOverride = (
  agentId: string,
  agent: AgentReadState & { lastReadAt: string | null },
  isFocused: boolean = false,
): AgentDotStatus => {
  const baseDotStatus = getAgentDotStatus(agent.status, agent.lastReadAt, agent.updatedAt, isFocused);
  return baseDotStatus === "read" && isUnreadOverrideActive(agentId, agent) ? "unread" : baseDotStatus;
};

// The user-facing "Mark as unread" action: record the override, flip the agent's
// lastReadAt optimistically so the dot updates immediately, and persist.
export const markAgentUnreadAtom = atom(null, (get, set, target: { workspaceId: string; agentId: string }): void => {
  const agent = get(agentAtomFamily(target.agentId));
  if (agent === null) {
    return;
  }
  setUnreadOverride(target.agentId, agent);
  set(agentAtomFamily(target.agentId), { ...agent, lastReadAt: null });
  markWorkspaceAgentUnread({ path: { workspace_id: target.workspaceId, agent_id: target.agentId } }).catch(() => {
    // Fire-and-forget: the server-authoritative value will arrive via WebSocket.
  });
});
