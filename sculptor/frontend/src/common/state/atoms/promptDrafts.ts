import { atomFamily } from "jotai/utils";

import type { AgentID } from "../ids.ts";
import { atomWithDebouncedStorage } from "./atomWithDebouncedStorage.ts";

// Debounced so that rapid typing does not synchronously block the main thread
// with localStorage writes on every keystroke.
export const promptDraftAtomFamily = atomFamily((agentId: AgentID) => {
  return atomWithDebouncedStorage<string | null>(`sculptor-prompt-draft-${agentId}`, null, 300);
});
