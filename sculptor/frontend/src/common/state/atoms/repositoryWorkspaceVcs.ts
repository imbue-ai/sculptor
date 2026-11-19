import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { projectJjStateAtomFamily } from "~/common/state/atoms/projectJjState.ts";
import { projectAtomFamily } from "~/common/state/atoms/projects.ts";
import {
  type JjAvailability,
  type RepositoryWorkspaceVcs,
  repositoryWorkspaceVcs,
} from "~/common/utils/workspaceModeRules.ts";

// `isJjAvailableAtom` reads an unknown status as unavailable; the create surfaces
// need to tell the two apart, to say jj is unavailable only once it is known.
const jjAvailabilityAtom = atom<JjAvailability>((get) => {
  const status = get(dependenciesStatusAtom);
  if (status === null) return "unknown";
  return status.jjReadiness.blocker === null ? "available" : "unavailable";
});

/** Which version control a repository's new isolated workspaces use, from the streamed project and its jj state. */
export const repositoryWorkspaceVcsAtomFamily = atomFamily<string, Atom<RepositoryWorkspaceVcs>>((projectId) =>
  atom<RepositoryWorkspaceVcs>((get) =>
    repositoryWorkspaceVcs({
      createsJjWorkspaces: get(projectJjStateAtomFamily(projectId))?.createsJjWorkspaces ?? false,
      usesJjForNewWorkspaces: get(projectAtomFamily(projectId))?.useJjForNewWorkspaces ?? false,
      jjAvailability: get(jjAvailabilityAtom),
    }),
  ),
);
