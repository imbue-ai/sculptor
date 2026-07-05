import { useAtom } from "jotai";
import type { SetStateAction } from "react";

import { attachedFilesAtomFamily } from "../atoms/attachedFiles.ts";
import type { AgentID } from "../ids.ts";

export const useDraftAttachedFiles = (
  agentId: AgentID,
): [Array<string>, (update: SetStateAction<Array<string>>) => void] => {
  return useAtom(attachedFilesAtomFamily(agentId));
};
