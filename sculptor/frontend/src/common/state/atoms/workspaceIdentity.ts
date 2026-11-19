import type { Atom } from "jotai";
import { atom } from "jotai";
import { atomFamily, selectAtom } from "jotai/utils";

import type { WorkspaceJjStateInfo } from "../../../api";
import type { WorkspaceVcs } from "../../utils/workspaceVcs.ts";
import { workspaceVcsOf } from "../../utils/workspaceVcs.ts";
import { workspaceBranchAtomFamily } from "./workspaceBranch.ts";
import { workspaceJjStateAtomFamily } from "./workspaceJjState.ts";
import { asLiveWorkspace, workspaceAtomFamily, workspaceIdsAtom } from "./workspaces.ts";

/** The streamed facts a workspace's identity label is resolved from. */
export type WorkspaceIdentitySources =
  | {
      vcs: "git";
      /** The checked-out branch the branch poller reports, or null until it has. */
      liveBranch: string | null;
      /** The branch the workspace was created to be on. */
      requestedBranchName: string | null;
    }
  | {
      vcs: "jj";
      /** The working copy and bookmarks the jj poller reports, or null until it has. */
      jjState: WorkspaceJjStateInfo | null;
      /** The bookmark Sculptor sets once the workspace has described work. */
      requestedBranchName: string | null;
    };

// Primitive slices of the workspace, so identity readers re-render when the
// requested name changes rather than on every workspace update.
const requestedBranchNameAtomFamily = atomFamily<string, Atom<string | null>>((workspaceId) =>
  selectAtom(workspaceAtomFamily(workspaceId), (entry) => asLiveWorkspace(entry)?.requestedBranchName ?? null),
);

const workspaceVcsAtomFamily = atomFamily<string, Atom<WorkspaceVcs | null>>((workspaceId) =>
  selectAtom(workspaceAtomFamily(workspaceId), (entry) => {
    const workspace = asLiveWorkspace(entry);
    return workspace === null ? null : workspaceVcsOf(workspace);
  }),
);

export const workspaceIdentitySourcesAtomFamily = atomFamily<string, Atom<WorkspaceIdentitySources>>((workspaceId) =>
  atom((get): WorkspaceIdentitySources => {
    const requestedBranchName = get(requestedBranchNameAtomFamily(workspaceId));
    if (get(workspaceVcsAtomFamily(workspaceId)) === "jj") {
      return { vcs: "jj", jjState: get(workspaceJjStateAtomFamily(workspaceId)), requestedBranchName };
    }
    // A workspace that has not streamed in yet resolves as git: the branch
    // poller's report is the only identity it can already have.
    return {
      vcs: "git",
      liveBranch: get(workspaceBranchAtomFamily(workspaceId))?.currentBranch ?? null,
      requestedBranchName,
    };
  }),
);

export const workspaceIdentitySourcesByIdAtom = atom<ReadonlyMap<string, WorkspaceIdentitySources>>(
  (get) => new Map((get(workspaceIdsAtom) ?? []).map((id) => [id, get(workspaceIdentitySourcesAtomFamily(id))])),
);
