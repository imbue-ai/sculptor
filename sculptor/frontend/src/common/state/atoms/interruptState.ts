import { atom, type PrimitiveAtom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { TaskID } from "../../Types.ts";

// Per-task "interrupt in flight" flag backing `useInterruptAgent`. The hook
// writes it through the Jotai store when a stop request fires and clears it
// once the request settles; reading the store first lets a second press
// early-return instead of firing a duplicate interrupt. Every stop surface
// (the keybinding in ChatInput, the Stop button on StatusPill, the
// interrupt-and-send in QueuedMessageBar) goes through the hook, so all
// reflect the same "Interrupting..." state. Transient; not persisted.
export const isInterruptingAtomFamily = atomFamily<TaskID, PrimitiveAtom<boolean>>(() => atom<boolean>(false));

// Per-task "Stop is clickable right now" flag. Mirrors `useAgentStatus().isCancellable`
// so the Ctrl+C keybinding in ChatInput fires under exactly the same conditions
// that render a clickable Stop button on StatusPill. Written by StatusPill (which
// owns the underlying state machine) and read by ChatInput's keybinding listener.
// False by default; cleared on StatusPill unmount.
export const isCancellableAtomFamily = atomFamily<TaskID, PrimitiveAtom<boolean>>(() => atom<boolean>(false));
