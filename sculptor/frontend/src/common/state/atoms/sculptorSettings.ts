import { atom } from "jotai";

import type { SculptorSettings } from "../../../api";

export const sculptorSettingsAtom = atom<SculptorSettings | null>(null);
