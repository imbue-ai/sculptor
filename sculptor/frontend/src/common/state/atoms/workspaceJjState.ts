import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";
import { isEqual } from "lodash";

import type { WorkspaceJjStateInfo } from "../../../api";
import { invalidateWorkspaceRevisionsQueries } from "../queryClient.ts";

/** A jj workspace's working copy and bookmarks; null until the stream describes it,
 * and always null for a git workspace. */
export const workspaceJjStateAtomFamily = atomFamily<string, PrimitiveAtom<WorkspaceJjStateInfo | null>>(() =>
  atom<WorkspaceJjStateInfo | null>(null),
);

/**
 * Apply the jj workspace states in a stream frame. Only the unified stream writes them.
 * A changed state also marks the workspace's cached revisions stale, since what changed
 * (a bookmark, a description) may leave the diff as it was.
 */
export const updateWorkspaceJjStatesAtom = atom(
  null,
  (get, set, jjStateByWorkspaceId: Readonly<Record<string, WorkspaceJjStateInfo>>) => {
    Object.entries(jjStateByWorkspaceId).forEach(([workspaceId, jjState]) => {
      const previous = get(workspaceJjStateAtomFamily(workspaceId));
      if (previous !== null && !isEqual(previous, jjState)) {
        invalidateWorkspaceRevisionsQueries(workspaceId);
      }
      set(workspaceJjStateAtomFamily(workspaceId), jjState);
    });
  },
);
