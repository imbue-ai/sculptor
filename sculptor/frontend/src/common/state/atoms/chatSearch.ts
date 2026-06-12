import { atom } from "jotai";

export const chatSearchVisibleAtom = atom<boolean>(false);

export const chatSearchQueryAtom = atom<string>("");

export const chatSearchActiveIndexAtom = atom<number>(0);

// Incremented each time the user presses Cmd+F to request focus on the search input.
// Listened to by AlphaChatInterface to focus and select the input text, even when
// the search bar is already visible.
export const chatSearchFocusRequestAtom = atom<number>(0);
