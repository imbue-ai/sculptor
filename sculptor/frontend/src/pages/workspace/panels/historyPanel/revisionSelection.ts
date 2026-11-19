import type { RevisionInfo } from "~/api";

type RevisionKey = Pick<RevisionInfo, "changeId" | "commitId">;

/**
 * The commit to show a selected revision's diff at. jj rewrites a revision's
 * commit on every snapshot while keeping its change id, so the selection
 * follows the change: the selected commit while it is still listed (which
 * also tells divergent revisions apart), else the commit its change now has,
 * else nothing once the change has left the list. Until the revisions load,
 * the selected commit.
 */
export const resolveSelectedRevisionCommitId = (inputs: {
  selection: RevisionKey;
  revisions: ReadonlyArray<RevisionKey> | undefined;
}): string | null => {
  const { selection, revisions } = inputs;
  if (revisions === undefined) {
    return selection.commitId;
  }

  if (revisions.some((revision) => revision.commitId === selection.commitId)) {
    return selection.commitId;
  }
  return revisions.find((revision) => revision.changeId === selection.changeId)?.commitId ?? null;
};
