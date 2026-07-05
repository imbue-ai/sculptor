import { useAtom } from "jotai";

import { promptDraftAtomFamily } from "../atoms/promptDrafts";
import type { TaskID } from "../ids.ts";

export const usePromptDraft = (taskId: TaskID): [string | null, (value: string | null) => void] => {
  return useAtom(promptDraftAtomFamily(taskId));
};
