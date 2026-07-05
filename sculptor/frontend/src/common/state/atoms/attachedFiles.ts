import type { PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { TaskID } from "../ids.ts";

export const attachedFilesAtomFamily = atomFamily<TaskID, PrimitiveAtom<Array<string>>>(
  (taskId): PrimitiveAtom<Array<string>> => {
    return atomWithStorage<Array<string>>(`sculptor-attached-files-${taskId}`, []);
  },
);
