import type { PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { AgentID } from "../ids.ts";

export const attachedFilesAtomFamily = atomFamily<AgentID, PrimitiveAtom<Array<string>>>(
  (agentId): PrimitiveAtom<Array<string>> => {
    return atomWithStorage<Array<string>>(`sculptor-attached-files-${agentId}`, []);
  },
);
