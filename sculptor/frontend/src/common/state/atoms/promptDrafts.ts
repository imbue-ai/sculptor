import { atomFamily } from "jotai/utils";

import type { TaskID } from "../../Types.ts";
import { atomWithDebouncedStorage } from "./atomWithDebouncedStorage.ts";

// Debounced so that rapid typing does not synchronously block the main thread
// with localStorage writes on every keystroke.
export const promptDraftAtomFamily = atomFamily((taskId: TaskID) => {
  return atomWithDebouncedStorage<string | null>(`sculptor-prompt-draft-${taskId}`, null, 300);
});
