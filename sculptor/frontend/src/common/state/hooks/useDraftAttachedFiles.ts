import { useAtom } from "jotai";
import type { SetStateAction } from "react";

import { attachedFilesAtomFamily } from "../atoms/attachedFiles.ts";
import type { TaskID } from "../ids.ts";

export const useDraftAttachedFiles = (
  taskId: TaskID,
): [Array<string>, (update: SetStateAction<Array<string>>) => void] => {
  return useAtom(attachedFilesAtomFamily(taskId));
};
