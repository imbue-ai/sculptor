// Sculptor opens and tracks pull requests on the origin remote.
const PR_REMOTE_NAME = "origin";

export const toRemoteRefName = (branchName: string): string => `${PR_REMOTE_NAME}/${branchName}`;

/**
 * The PR base branch that PR status matches a target ref against. It mirrors
 * the backend's `strip_remote_prefix`, local `feature/login` → `login`
 * included, because frontend checks of whether a reported PR still targets
 * another branch must agree with the backend. Change the two together.
 */
export const toPrBaseRefName = (targetRef: string): string => {
  const firstSlashIndex = targetRef.indexOf("/");
  return firstSlashIndex === -1 ? targetRef : targetRef.slice(firstSlashIndex + 1);
};
