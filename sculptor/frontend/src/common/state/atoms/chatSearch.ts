import { atom } from "jotai";

export const chatSearchVisibleAtom = atom<boolean>(false);

export const chatSearchQueryAtom = atom<string>("");

export const chatSearchActiveIndexAtom = atom<number>(0);

// Incremented to request focus on the search input. The visible search bar
// re-focuses and selects its input in response, so Cmd+F refocuses the search
// even when the bar is already visible.
export const chatSearchFocusRequestAtom = atom<number>(0);
