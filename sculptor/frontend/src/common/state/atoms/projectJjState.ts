import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { ProjectJjState } from "../../../api";

/** A repository's jj colocation and whether it creates jj workspaces; null until
 * the stream describes it. */
export const projectJjStateAtomFamily = atomFamily<string, PrimitiveAtom<ProjectJjState | null>>(() =>
  atom<ProjectJjState | null>(null),
);

/** Apply the repository jj states in a stream frame. Only the unified stream writes them. */
export const updateProjectJjStatesAtom = atom(
  null,
  (_get, set, jjStateByProjectId: Readonly<Record<string, ProjectJjState>>) => {
    Object.entries(jjStateByProjectId).forEach(([projectId, jjState]) => {
      set(projectJjStateAtomFamily(projectId), jjState);
    });
  },
);
