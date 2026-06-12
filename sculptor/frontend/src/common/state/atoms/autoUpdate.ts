import { atom } from "jotai";

import type { AutoUpdateStatus, UpdateChannel } from "~/shared/types.ts";

export const autoUpdateStatusAtom = atom<AutoUpdateStatus | null>(null);
export const updateChannelAtom = atom<UpdateChannel | null>(null);
export const isInstallingUpdateAtom = atom(false);
