// Sculptor opens and tracks pull requests on the origin remote.
const PR_REMOTE_NAME = "origin";

/** The remote-tracking ref for a branch on the pull-request remote: `main` → `origin/main`. */
export const toRemoteRefName = (branchName: string): string => `${PR_REMOTE_NAME}/${branchName}`;

/**
 * The PR base branch that PR status matches a target ref against: the ref
 * without its first path segment, so `origin/main` → `main`. This mirrors the
 * backend's `strip_remote_prefix`, which also turns a local `feature/login`
 * into `login`. Frontend checks of whether a reported PR still targets another
 * branch must use the same rule as the backend, so change the two together.
 */
export const toPrBaseRefName = (targetRef: string): string => {
  const firstSlashIndex = targetRef.indexOf("/");
  return firstSlashIndex === -1 ? targetRef : targetRef.slice(firstSlashIndex + 1);
};
