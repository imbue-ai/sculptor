import { atom } from "jotai";

export const devPanelOpenAtom = atom(false);

export const reactGrabEnabledAtom = atom(false);

export const tanstackDevtoolsEnabledAtom = atom(false);

export type TanstackDevtoolsMode = "floating" | "docked-bottom";

export const tanstackDevtoolsModeAtom = atom<TanstackDevtoolsMode>("floating");

export const tanstackEventLogEnabledAtom = atom(false);
