// Sculptor opens and tracks pull requests on the origin remote.
const PR_REMOTE_NAME = "origin";

const PR_REMOTE_PREFIX = `${PR_REMOTE_NAME}/`;

/** The remote-tracking ref for a branch on the pull-request remote: `main` → `origin/main`. */
export const toRemoteRefName = (branchName: string): string => `${PR_REMOTE_PREFIX}${branchName}`;

/**
 * The branch name the code host uses for a ref: `origin/main` → `main`. Only the
 * pull-request remote is stripped, so a local `feature/login` keeps its full name.
 */
export const toBareRefName = (refName: string): string =>
  refName.startsWith(PR_REMOTE_PREFIX) ? refName.slice(PR_REMOTE_PREFIX.length) : refName;
