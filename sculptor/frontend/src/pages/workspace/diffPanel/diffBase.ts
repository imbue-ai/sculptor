import type { DiffArtifact } from "~/api";

import type { DiffScope } from "./types/diffPanel.ts";

/**
 * The commit a scope's diff was taken against, as the backend names it on the
 * diff artifact: the before-image of every file in that diff is read at this
 * commit. Null when the diff has no single base (a merge, or no target), and
 * then the viewer shows the diff text without a before-image.
 */
export const diffBaseCommitId = (inputs: {
  diff: Pick<DiffArtifact, "uncommittedDiffBase" | "targetBranchMergeBase"> | null | undefined;
  scope: DiffScope;
}): string | null => {
  const base =
    inputs.scope === "vs-target-branch" ? inputs.diff?.targetBranchMergeBase : inputs.diff?.uncommittedDiffBase;
  return base || null;
};
