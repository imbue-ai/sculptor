import { atom } from "jotai";

// Counts how many chat panels (real or skeleton) are currently mounted. Chat-panel
// components increment on mount and decrement on unmount, giving the rest of the app a
// reactive, DOM-free signal that can be read from React render paths (e.g. the command
// palette's visibility filter). It is a counter rather than a boolean because the section
// layout can mount two chat panels at once; the count stays correct when one unmounts.
export const chatPanelMountedAtom = atom<number>(0);

// Same pattern for terminal panels — incremented by `TerminalPanelView` so commands like
// "Clear terminal" can gate their visibility on whether a terminal is mounted. A counter
// because multiple terminal panels can be mounted simultaneously.
export const terminalPanelMountedAtom = atom<number>(0);
