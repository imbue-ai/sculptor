import { atom } from "jotai";

import type { DependenciesStatus } from "../../../api";

export const dependenciesStatusAtom = atom<DependenciesStatus | null>(null);
