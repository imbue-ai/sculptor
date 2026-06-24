import { atom } from "jotai";

// Tracks whether a chat panel (real or skeleton) is currently mounted. Chat-panel
// components flip this to `true` on mount and `false` on unmount, giving the rest of
// the app a reactive, DOM-free signal that can be read from React render paths (e.g.
// the command palette's visibility filter).
export const chatPanelMountedAtom = atom<boolean>(false);

// Same pattern for the terminal panel — flipped by `TerminalPanelContent` so commands
// like "Clear terminal" can gate their visibility on whether there's a terminal to act
// on at all.
export const terminalPanelMountedAtom = atom<boolean>(false);
