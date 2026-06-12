import type { PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { TaskID } from "../../Types.ts";

export const attachedFilesAtomFamily = atomFamily<TaskID, PrimitiveAtom<Array<string>>>((taskId) => {
  return atomWithStorage<Array<string>>(`sculptor-attached-files-${taskId}`, []);
});
