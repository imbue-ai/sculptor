import { useEffect, useState } from "react";

import { useWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";

// How long to show the branch skeleton before falling back to the source branch.
// The workspace's current branch normally streams in well under this. The cap
// exists because the branch poller only publishes a current branch for a
// workspace whose git working directory resolves — a workspace whose
// environment was never created (no agent has ever run) or whose worktree is
// gone never emits one. Without a cap those rows, which do appear in the recent
// list, would pulse a skeleton forever; after the grace window they fall back to
// the source branch instead.
export const BRANCH_LOAD_GRACE_MS = 2000;

export type WorkspaceRowBranch = {
  // The branch to display, or null when none is known (no current branch and no
  // source branch). The row renders nothing for null.
  branch: string | null;
  // True only while still waiting for the current branch within the grace
  // window — the row shows a skeleton then.
  isLoading: boolean;
};

/**
 * Resolve the branch label for a recent-workspace row.
 *
 * Prefers the workspace's own current branch, which streams in over the
 * WebSocket. Until it arrives this reports `isLoading` so the row can show a
 * skeleton rather than flashing `sourceBranch` — the DIFFERENT base branch the
 * workspace was forked from. If the current branch hasn't arrived within
 * {@link BRANCH_LOAD_GRACE_MS} it falls back to `sourceBranch`, so the skeleton
 * can never become permanent for a workspace whose branch is never published.
 */
export const useWorkspaceRowBranch = (workspaceId: string, sourceBranch: string | null): WorkspaceRowBranch => {
  const branchInfo = useWorkspaceBranch(workspaceId);
  const currentBranch = branchInfo?.currentBranch;
  const [hasGraceElapsed, setHasGraceElapsed] = useState(false);

  useEffect(() => {
    // Once the current branch is known there is nothing to wait for; the effect
    // cleanup clears any pending timer from the loading window.
    if (currentBranch !== undefined) {
      return undefined;
    }
    const timer = setTimeout((): void => setHasGraceElapsed(true), BRANCH_LOAD_GRACE_MS);
    return (): void => clearTimeout(timer);
  }, [currentBranch]);

  if (currentBranch !== undefined) {
    return { branch: currentBranch, isLoading: false };
  }

  if (hasGraceElapsed) {
    return { branch: sourceBranch, isLoading: false };
  }
  return { branch: null, isLoading: true };
};
