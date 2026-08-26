import { useAtom } from "jotai";

import type { TaskID } from "../../Types.ts";
import { promptDraftAtomFamily } from "../atoms/promptDrafts";

export const usePromptDraft = (taskId: TaskID): [string | null, (value: string | null) => void] => {
  return useAtom(promptDraftAtomFamily(taskId));
};
