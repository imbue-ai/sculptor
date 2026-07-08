import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";

// The task atoms are legacy read models: the TanStack Query cache is the
// written store for task state, and useTaskQueryMirror projects it into these
// atoms for the remaining Jotai readers. Nothing else should write them.

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

// Fine-grained derived atoms for commonly-read task fields.
// Components subscribing to these only re-render when the specific field changes.
// Jotai uses Object.is for primitive comparisons, so string/boolean fields that
// stay the same across a task object update will not notify subscribers.

export const taskStatusAtomFamily = atomFamily<string, Atom<TaskStatus | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.status),
);

// Terminal agents carry no model (`model` is null); treat that the same as "unknown".
export const taskModelAtomFamily = atomFamily<string, Atom<string | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.model ?? undefined),
);

// The workspace that owns the task — immutable once the task view has loaded,
// so subscribers re-render only on load/removal, never on task churn (status,
// timestamps, artifacts, ...).
export const taskWorkspaceIdAtomFamily = atomFamily<string, Atom<string | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.workspaceId ?? undefined),
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

// Whether the harness sources its switcher catalog from a backend (pi). A
// non-capability view field, so the no-direct-harness-capability-read ratchet
// does not apply.
export const taskSourcesBackendModelsAtomFamily = atomFamily<string, Atom<boolean>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.sourcesBackendModels ?? false),
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
