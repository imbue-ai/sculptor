import { atom, type PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { TaskID } from "../../Types.ts";

/**
 * Per-task state for the StatusPill agent-tasks widget. These atoms persist
 * across workspace-tab switches (because Jotai atoms outlive component mounts)
 * and the localStorage-backed ones additionally survive a full app restart.
 *
 * Without persistence, the phase machine and the "is this artifact stale?"
 * check would re-derive incorrectly after a remount — e.g. a TodoWrite
 * artifact carried over from a previous turn would be mis-attributed to the
 * new turn after restart.
 */

export type TasksPhase = "idle" | "active" | "lingering";

/** Engagement phase. In-memory only — survives tab switches but resets on
 * full app restart, which is fine because the effect-driven re-derivation
 * from the artifact + persisted turn ids puts it back into the right state. */
export const tasksPhaseAtomFamily = atomFamily<TaskID, PrimitiveAtom<TasksPhase>>(() => atom<TasksPhase>("idle"));

/** Most recent turn id during which an in-progress task was observed. Used
 * to detect when an all-complete artifact is a stale carryover from a
 * previous turn. Persisted so the staleness check is correct after restart. */
export const liveTaskTurnIdAtomFamily = atomFamily<TaskID, PrimitiveAtom<string | null>>((taskId) =>
  atomWithStorage<string | null>(`sculptor-tasks-pill-live-turn-${taskId}`, null),
);

/** Latched workingUserMessageId (the "active turn"). Persisted because the
 * elapsed timer keys off it and the staleness check compares against it;
 * losing this on restart would cause the timer to reset and the wrong
 * artifact-freshness verdict on a brand-new turn. */
export const activeTurnIdAtomFamily = atomFamily<TaskID, PrimitiveAtom<string | null>>((taskId) =>
  atomWithStorage<string | null>(`sculptor-tasks-pill-active-turn-${taskId}`, null),
);
