import { useAtom } from "jotai";

import type { TaskID } from "../../Types.ts";
import { attachedFilesAtomFamily } from "../atoms/attachedFiles.ts";

// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
export const useDraftAttachedFiles = (taskId: TaskID) => {
  return useAtom(attachedFilesAtomFamily(taskId));
};
