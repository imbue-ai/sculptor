import { atom, type PrimitiveAtom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { TaskID } from "../../Types.ts";

// Per-task "interrupt in flight" flag, shared between the Stop button on
// ThinkingIndicator and the Esc keybinding handler in ChatInput. Both
// surfaces need to debounce against a stale `isAgentBusy` (which can stay
// true for a beat after the API call) and reflect the same "Stopping..."
// visual state. Transient; not persisted.
export const isInterruptingAtomFamily = atomFamily<TaskID, PrimitiveAtom<boolean>>(() => atom<boolean>(false));

// Per-task "Stop is clickable right now" flag. Mirrors `useAgentStatus().isCancellable`
// so the Ctrl+C keybinding in ChatInput fires under exactly the same conditions
// that render a clickable Stop button on StatusPill. Written by StatusPill (which
// owns the underlying state machine) and read by ChatInput's keybinding listener.
// False by default; cleared on StatusPill unmount.
export const isCancellableAtomFamily = atomFamily<TaskID, PrimitiveAtom<boolean>>(() => atom<boolean>(false));
