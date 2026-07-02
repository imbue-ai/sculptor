import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";
import { isEqual } from "lodash";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";
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

    // Skip atom update when the task data hasn't changed to avoid unnecessary re-renders.
    const current = get(taskAtomFamily(id));
    if (!isEqual(current, task)) {
      set(taskAtomFamily(id), task);
    }

    if (!seenIds.has(id)) {
      seenIds.add(id);
      didIdsChange = true;
    }
  });

  // Write even when nothing changed if the list is still undefined: every
  // stream frame carries a task-view map, so the first one — empty in a
  // zero-task instance — marks the list as loaded. Consumers rely on the
  // undefined → array transition to tell "still loading" from "no tasks"
  // (e.g. WorkspacePage's agentless-workspace gate).
  if (didIdsChange || get(taskIdsAtom) === undefined) {
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

// A stable reference for the "no backend list" case, so the derived atom below
// keeps one identity across unrelated task updates instead of a fresh array each
// recompute.
const EMPTY_MODEL_OPTIONS: ReadonlyArray<ModelOption> = [];

// The harness's backend-sourced model catalog (pi). A non-capability view field,
// so the no-direct-harness-capability-read ratchet does not apply. Empty for
// harnesses that source no list (Claude) — the switcher then falls back to its
// built-in PRODUCTION_MODELS.
export const taskAvailableModelsAtomFamily = atomFamily<string, Atom<ReadonlyArray<ModelOption>>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.availableModels ?? EMPTY_MODEL_OPTIONS),
);

// The model_id the switcher should show as selected for a backend-sourced list
// (pi), or undefined when the harness tracks no per-task selection.
export const taskSelectedModelIdAtomFamily = atomFamily<string, Atom<string | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.selectedModelId ?? undefined),
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

export const taskSupportsChatInterfaceAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsChatInterface),
);

export const taskSupportsModelSelectionAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsModelSelection),
);

export const taskAcceptsAutomatedPromptsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.acceptsAutomatedPrompts),
);
