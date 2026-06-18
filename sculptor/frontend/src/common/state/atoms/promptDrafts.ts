import type { PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { TaskID } from "../../Types.ts";
import { atomWithDebouncedStorage } from "./atomWithDebouncedStorage.ts";

// Debounced so that rapid typing does not synchronously block the main thread
// with localStorage writes on every keystroke.
export const promptDraftAtomFamily = atomFamily((taskId: TaskID) => {
  return atomWithDebouncedStorage<string | null>(`sculptor-prompt-draft-${taskId}`, null, 300);
});

/** Workspace name draft keyed by new-workspace tab draft ID. */
export const draftTabNameAtomFamily = atomFamily<string, PrimitiveAtom<string | null>>((draftId) => {
  return atomWithStorage<string | null>(`sculptor-draft-tab-name-${draftId}`, null);
});

// The repo/branch drafts below mirror the workspace-name draft so the whole
// new-workspace form survives a tab switch (the page unmounts when another tab
// is shown and remounts on return). They use `getOnInit: true` so the stored
// value is read synchronously on mount, before AddWorkspacePage's project-load
// effect runs — otherwise that effect would clobber a restored repo selection
// with the most-recently-used default. See SCU-1427.

/** Selected repo (project ID) draft keyed by new-workspace tab draft ID. */
export const draftProjectIdAtomFamily = atomFamily<string, PrimitiveAtom<string | null>>((draftId) => {
  return atomWithStorage<string | null>(`sculptor-draft-project-id-${draftId}`, null, undefined, { getOnInit: true });
});

/** Selected source-branch draft keyed by new-workspace tab draft ID. */
export const draftSourceBranchAtomFamily = atomFamily<string, PrimitiveAtom<string | null>>((draftId) => {
  return atomWithStorage<string | null>(`sculptor-draft-source-branch-${draftId}`, null, undefined, {
    getOnInit: true,
  });
});

/** Manually-edited branch-name override draft keyed by new-workspace tab draft ID. */
export const draftBranchNameOverrideAtomFamily = atomFamily<string, PrimitiveAtom<string | null>>((draftId) => {
  return atomWithStorage<string | null>(`sculptor-draft-branch-name-${draftId}`, null, undefined, {
    getOnInit: true,
  });
});
