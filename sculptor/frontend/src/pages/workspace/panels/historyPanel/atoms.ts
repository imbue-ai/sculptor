import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

/** Stores the set of expanded commit hashes per workspace. */
export const expandedCommitsAtomFamily = atomFamily((_workspaceId: string) => atom<Set<string>>(new Set<string>()));

/** Collapse all expanded commits. */
export const collapseAllCommitsAtom = atom(null, (get, set, { workspaceId }: { workspaceId: string }): void => {
  const expandedAtom = expandedCommitsAtomFamily(workspaceId);
  set(expandedAtom, new Set<string>());
});

/** Toggle a commit's expanded state. */
export const toggleCommitExpandedAtom = atom(
  null,
  (get, set, { workspaceId, commitHash }: { workspaceId: string; commitHash: string }): void => {
    const expandedAtom = expandedCommitsAtomFamily(workspaceId);
    const current = get(expandedAtom);
    const next = new Set(current);
    if (next.has(commitHash)) {
      next.delete(commitHash);
    } else {
      next.add(commitHash);
    }
    set(expandedAtom, next);
  },
);
