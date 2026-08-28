import { useAtom } from "jotai";

import { promptDraftAtomFamily } from "../atoms/promptDrafts";
import type { AgentID } from "../ids.ts";

export const usePromptDraft = (agentId: AgentID): [string | null, (value: string | null) => void] => {
  return useAtom(promptDraftAtomFamily(agentId));
};
