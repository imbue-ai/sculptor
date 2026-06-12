import type { PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { EffortLevel, LlmModel } from "../../../api";
import type { TaskID } from "../../Types.ts";

/**
 * Per-task fast-mode, effort, and model preference, persisted to localStorage
 * so it survives reloads, Electron relaunches after sleep, and hot-reloads.
 *
 * `null` means "not yet initialized for this task" — the ChatInput mount
 * effect seeds the user's current default once `userConfig` is loaded.
 */

const fastModeStorageKey = (taskId: TaskID): string => `sculptor-fast-mode-${taskId}`;
const effortStorageKey = (taskId: TaskID): string => `sculptor-effort-${taskId}`;
const modelStorageKey = (taskId: TaskID): string => `sculptor-model-${taskId}`;

export const fastModeAtomFamily = atomFamily<TaskID, PrimitiveAtom<boolean | null>>((taskId) =>
  atomWithStorage<boolean | null>(fastModeStorageKey(taskId), null),
);

export const effortAtomFamily = atomFamily<TaskID, PrimitiveAtom<EffortLevel | null>>((taskId) =>
  atomWithStorage<EffortLevel | null>(effortStorageKey(taskId), null),
);

export const modelAtomFamily = atomFamily<TaskID, PrimitiveAtom<LlmModel | null>>((taskId) =>
  atomWithStorage<LlmModel | null>(modelStorageKey(taskId), null),
);

/** Drop per-task stored preferences when a task is deleted. */
export const removeTaskSettings = (taskId: TaskID): void => {
  localStorage.removeItem(fastModeStorageKey(taskId));
  localStorage.removeItem(effortStorageKey(taskId));
  localStorage.removeItem(modelStorageKey(taskId));
  fastModeAtomFamily.remove(taskId);
  effortAtomFamily.remove(taskId);
  modelAtomFamily.remove(taskId);
};
