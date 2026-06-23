import { atom } from "jotai";

export const devPanelOpenAtom = atom<boolean>(false);

export const reactGrabEnabledAtom = atom<boolean>(false);

export const tanstackDevtoolsEnabledAtom = atom<boolean>(false);

export type TanstackDevtoolsMode = "floating" | "docked-bottom";

export const tanstackDevtoolsModeAtom = atom<TanstackDevtoolsMode>("floating");

export const tanstackEventLogEnabledAtom = atom<boolean>(false);
