import { useAtom } from "jotai";
import type { SetStateAction } from "react";

import type { TaskID } from "../../Types.ts";
import { attachedFilesAtomFamily } from "../atoms/attachedFiles.ts";

export const useDraftAttachedFiles = (
  taskId: TaskID,
): [Array<string>, (update: SetStateAction<Array<string>>) => void] => {
  return useAtom(attachedFilesAtomFamily(taskId));
};
