/**
 * Get the branch name to display for a task.
 */
export const getBranchName = (branchNameFromRepo: string | null | undefined): string | null => {
  return branchNameFromRepo ?? null;
};
