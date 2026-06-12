import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { RepoInfo } from "../../../api";
import type { ProjectID } from "../../Types.ts";

export const repoInfoAtomFamily = atomFamily<ProjectID, PrimitiveAtom<RepoInfo | null>>(() =>
  atom<RepoInfo | null>(null),
);
