import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";
import { isEqual } from "lodash";

import type { CodingAgentTaskView, TaskStatus } from "../../../api";
import { removeTaskSettings } from "./draftAgentSettings.ts";

export const taskAtomFamily = atomFamily<string, PrimitiveAtom<CodingAgentTaskView | null>>(() =>
  atom<CodingAgentTaskView | null>(null),
);

export const taskIdsAtom = atom<ReadonlyArray<string> | undefined>(undefined);

export const tasksArrayAtom = atom<ReadonlyArray<CodingAgentTaskView> | undefined>((get) => {
  const taskIds = get(taskIdsAtom);
  if (taskIds === undefined) {
    return undefined;
  }
  return taskIds
    .map((id) => get(taskAtomFamily(id)))
    .filter((task): task is CodingAgentTaskView => task !== null && !task.isDeleted);
});

export const updateTasksAtom = atom(null, (get, set, updates: Record<string, CodingAgentTaskView>) => {
  const seenIds = new Set(get(taskIdsAtom));
  let didIdsChange = false;

  Object.entries(updates).forEach(([id, task]) => {
    if (task.isDeleted) {
      if (seenIds.has(id)) {
        seenIds.delete(id);
        didIdsChange = true;
      }
      set(taskAtomFamily(id), null);
      removeTaskSettings(id);
      return;
    }

    const current = get(taskAtomFamily(id));
    // Ignore a view strictly older than what we already hold. Task-view frames
    // carry a monotonically increasing `updatedAt`, so an older one is stale /
    // out-of-order — e.g. the `createWorkspaceAgent` REST snapshot (captured at
    // creation time, status BUILDING) resolving AFTER the WebSocket already
    // settled the agent. Applying it would regress live state; this is what left
    // a freshly-created agent's status dot stuck on blue/"building" when other
    // sessions were already running.
    const isStale = current !== null && new Date(task.updatedAt).getTime() < new Date(current.updatedAt).getTime();
    // Skip the atom write when stale, or when unchanged (avoid needless re-renders).
    if (!isStale && !isEqual(current, task)) {
      set(taskAtomFamily(id), task);
    }

    if (!seenIds.has(id)) {
      seenIds.add(id);
      didIdsChange = true;
    }
  });

  if (didIdsChange) {
    set(taskIdsAtom, Array.from(seenIds));
  }
});

export const optimisticDeleteTaskAtom = atom(null, (get, set, taskId: string): CodingAgentTaskView | null => {
  const task = get(taskAtomFamily(taskId));
  if (task === null) {
    return null;
  }
  const snapshot = task;
  set(taskAtomFamily(taskId), null);
  const currentIds = get(taskIdsAtom) ?? [];
  set(
    taskIdsAtom,
    currentIds.filter((id) => id !== taskId),
  );
  return snapshot;
});

export const rollbackDeleteTaskAtom = atom(
  null,
  (get, set, { taskId, snapshot }: { taskId: string; snapshot: CodingAgentTaskView }): void => {
    set(taskAtomFamily(taskId), snapshot);
    const currentIds = get(taskIdsAtom) ?? [];
    if (!currentIds.includes(taskId)) {
      set(taskIdsAtom, [...currentIds, taskId]);
    }
  },
);

// Holds optimistic agent titles by agent id while a rename is in flight (and for a
// short trailing window after, to mask stale WebSocket pushes — see the comment in
// AgentTabs.tsx where this is set). Both AgentTabs and the chat intro read from this
// atom so the tab label and intro text update in lockstep instead of the intro waiting
// for the rename round-trip to update taskAtomFamily.
export const pendingAgentTitlesAtom = atom<Readonly<Record<string, string>>>({});

// Fine-grained derived atoms for commonly-read task fields.
// Components subscribing to these only re-render when the specific field changes.
// Jotai uses Object.is for primitive comparisons, so string/boolean fields that
// stay the same across a task object update will not notify subscribers.

export const taskStatusAtomFamily = atomFamily<string, Atom<TaskStatus | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.status),
);

export const taskModelAtomFamily = atomFamily<string, Atom<string | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.model),
);

export const taskIsAutoCompactingAtomFamily = atomFamily<string, Atom<boolean>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.isAutoCompacting ?? false),
);

export const taskSupportsInteractiveBackchannelAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsInteractiveBackchannel),
);

export const taskSupportsFastModeAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsFastMode),
);

export const taskSupportsFileAttachmentsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsFileAttachments),
);

export const taskSupportsImageInputAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsImageInput),
);

export const taskSupportsSkillsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsSkills),
);

export const taskSupportsSubAgentsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsSubAgents),
);

export const taskSupportsInterruptionAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsInterruption),
);

export const taskSupportsFileReferencesAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsFileReferences),
);

export const taskSupportsContextResetAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsContextReset),
);

export const taskSupportsCompactionAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsCompaction),
);

export const taskSupportsBackgroundTasksAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsBackgroundTasks),
);

export const taskSupportsSessionResumeAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsSessionResume),
);

export const taskSupportsToolUseRenderingAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsToolUseRendering),
);
