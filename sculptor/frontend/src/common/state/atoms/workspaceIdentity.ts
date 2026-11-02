import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";

import { workspaceBranchAtomFamily } from "./workspaceBranch.ts";
import { asLiveWorkspace, workspaceAtomFamily } from "./workspaces.ts";

/** The streamed facts a workspace's identity label is resolved from. */
export type WorkspaceIdentitySources = {
  /** The checked-out branch the branch poller reports, or null until it has. */
  liveBranch: string | null;
  /** The branch the workspace was created to be on. */
  requestedBranchName: string | null;
};

// A primitive slice of the workspace, so identity readers re-render when the
// requested name changes rather than on every workspace update.
const requestedBranchNameAtomFamily = atomFamily<string, Atom<string | null>>((workspaceId) =>
  selectAtom(workspaceAtomFamily(workspaceId), (entry) => asLiveWorkspace(entry)?.requestedBranchName ?? null),
);

export const workspaceIdentitySourcesAtomFamily = atomFamily<string, Atom<WorkspaceIdentitySources>>((workspaceId) =>
  atom((get) => ({
    liveBranch: get(workspaceBranchAtomFamily(workspaceId))?.currentBranch ?? null,
    requestedBranchName: get(requestedBranchNameAtomFamily(workspaceId)),
  })),
);
