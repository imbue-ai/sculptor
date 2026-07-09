import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { CodingAgentTaskView, TaskStatus } from "../../../api";

// The task atoms are legacy read models: the TanStack Query cache is the
// written store for task state, and useTaskQueryMirror projects it into these
// atoms for the remaining Jotai readers. Nothing else should write them.
//
// React components read per-task fields through the `useTask*` hooks in
// `hooks/useTaskHelpers.ts` (select-based reads of the query cache). The
// selector families that survive here exist ONLY for atom-graph readers that
// derive from them inside Jotai `get(...)` — `workspaceAgentActions.ts` and
// `mentionDetails.ts`. When those derivations move off Jotai, these go too.

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

// Fine-grained derived atoms for task fields still read inside Jotai atom
// graphs. Components subscribing to these only re-render when the specific
// field changes. Jotai uses Object.is for primitive comparisons, so string/
// boolean fields that stay the same across a task object update will not
// notify subscribers.

export const taskStatusAtomFamily = atomFamily<string, Atom<TaskStatus | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.status),
);

// Terminal agents carry no model (`model` is null); treat that the same as "unknown".
export const taskModelAtomFamily = atomFamily<string, Atom<string | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.model ?? undefined),
);

export const taskSupportsChatInterfaceAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.harnessCapabilities.supportsChatInterface),
);

export const taskAcceptsAutomatedPromptsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((taskId) =>
  atom((get) => get(taskAtomFamily(taskId))?.acceptsAutomatedPrompts),
);
