/**
 * Returns the workspace's current branch, normalizing an absent branch
 * (loading or unavailable) to `null` so callers render a single empty state.
 */
export const getBranchName = (branchNameFromRepo: string | null | undefined): string | null => {
  return branchNameFromRepo ?? null;
};
