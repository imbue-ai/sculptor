import { useAtom } from "jotai";

import type { TaskID } from "../../Types.ts";
import {
  draftBranchNameOverrideAtomFamily,
  draftProjectIdAtomFamily,
  draftSourceBranchAtomFamily,
  draftTabNameAtomFamily,
  promptDraftAtomFamily,
} from "../atoms/promptDrafts";

export const usePromptDraft = (taskId: TaskID): [string | null, (value: string | null) => void] => {
  return useAtom(promptDraftAtomFamily(taskId));
};

export const useDraftTabName = (draftId: string): [string | null, (value: string | null) => void] => {
  return useAtom(draftTabNameAtomFamily(draftId));
};

export const useDraftProjectId = (draftId: string): [string | null, (value: string | null) => void] => {
  return useAtom(draftProjectIdAtomFamily(draftId));
};

export const useDraftSourceBranch = (draftId: string): [string | null, (value: string | null) => void] => {
  return useAtom(draftSourceBranchAtomFamily(draftId));
};

export const useDraftBranchNameOverride = (draftId: string): [string | null, (value: string | null) => void] => {
  return useAtom(draftBranchNameOverrideAtomFamily(draftId));
};
