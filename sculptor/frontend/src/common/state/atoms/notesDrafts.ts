import { atomFamily } from "jotai/utils";

import { atomWithDebouncedStorage } from "./atomWithDebouncedStorage.ts";

// Debounced so that rapid typing does not synchronously block the main thread
// with localStorage writes on every keystroke.
export const notesDraftAtomFamily = atomFamily((workspaceID: string) => {
  return atomWithDebouncedStorage<string>(`sculptor-notes-draft-${workspaceID}`, "", 300);
});
