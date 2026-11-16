import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import { isJjAvailableAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { projectJjStateAtomFamily } from "~/common/state/atoms/projectJjState.ts";
import { projectAtomFamily } from "~/common/state/atoms/projects.ts";
import { type RepositoryWorkspaceVcs, repositoryWorkspaceVcs } from "~/common/utils/workspaceModeRules.ts";

/** Which version control a repository's new isolated workspaces use, from the streamed project and its jj state. */
export const repositoryWorkspaceVcsAtomFamily = atomFamily<string, Atom<RepositoryWorkspaceVcs>>((projectId) =>
  atom<RepositoryWorkspaceVcs>((get) =>
    repositoryWorkspaceVcs({
      createsJjWorkspaces: get(projectJjStateAtomFamily(projectId))?.createsJjWorkspaces ?? false,
      usesJjForNewWorkspaces: get(projectAtomFamily(projectId))?.useJjForNewWorkspaces ?? false,
      isJjAvailable: get(isJjAvailableAtom),
    }),
  ),
);
