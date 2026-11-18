import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { WorkspaceJjStateInfo } from "../../../api";

/** A jj workspace's working copy and bookmarks; null until the stream describes it,
 * and always null for a git workspace. */
export const workspaceJjStateAtomFamily = atomFamily<string, PrimitiveAtom<WorkspaceJjStateInfo | null>>(() =>
  atom<WorkspaceJjStateInfo | null>(null),
);

/** Apply the jj workspace states in a stream frame. Only the unified stream writes them. */
export const updateWorkspaceJjStatesAtom = atom(
  null,
  (_get, set, jjStateByWorkspaceId: Readonly<Record<string, WorkspaceJjStateInfo>>) => {
    Object.entries(jjStateByWorkspaceId).forEach(([workspaceId, jjState]) => {
      set(workspaceJjStateAtomFamily(workspaceId), jjState);
    });
  },
);
