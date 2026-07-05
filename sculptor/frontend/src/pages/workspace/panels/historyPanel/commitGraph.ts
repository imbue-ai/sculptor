import type { CommitInfo } from "~/api";

/** Number of leading characters shown for a commit hash in a graph label. */
export const SHORT_HASH_LENGTH = 11;

/**
 * Result of splitting a flat commit list into a main line and side branches.
 *
 * - `mainLine`: commits on the first-parent chain from HEAD.
 * - `sideBranches`: for each merge commit hash, the list of commits reachable
 *   only via the second parent (i.e. the "merged-in" sub-branch).
 */
export type CommitGraph = {
  mainLine: Array<CommitInfo>;
  sideBranches: Map<string, Array<CommitInfo>>;
};

/**
 * Walk the first-parent chain from commits[0] to identify the main line,
 * then assign remaining commits to the merge that brought them in.
 */
export function buildCommitGraph(commits: Array<CommitInfo>): CommitGraph {
  if (commits.length === 0) {
    return { mainLine: [], sideBranches: new Map() };
  }

  const byHash = new Map<string, CommitInfo>();
  for (const c of commits) {
    byHash.set(c.hash, c);
  }

  // Walk first-parent chain to build the main line.
  const mainLineHashes = new Set<string>();
  const mainLine: Array<CommitInfo> = [];
  let current: CommitInfo | undefined = commits[0];
  while (current) {
    mainLineHashes.add(current.hash);
    mainLine.push(current);
    const firstParent: string | undefined = current.parentHashes[0];
    current = firstParent ? byHash.get(firstParent) : undefined;
  }

  // For each merge on the main line, collect its second-parent chain.
  const claimed = new Set(mainLineHashes);
  const sideBranches = new Map<string, Array<CommitInfo>>();

  for (const commit of mainLine) {
    if (commit.parentHashes.length <= 1) continue;

    const secondParent = commit.parentHashes[1];
    const branch: Array<CommitInfo> = [];
    let node = byHash.get(secondParent);
    while (node && !claimed.has(node.hash)) {
      claimed.add(node.hash);
      branch.push(node);
      const next = node.parentHashes[0];
      node = next ? byHash.get(next) : undefined;
    }

    if (branch.length > 0) {
      sideBranches.set(commit.hash, branch);
    }
  }

  return { mainLine, sideBranches };
}
