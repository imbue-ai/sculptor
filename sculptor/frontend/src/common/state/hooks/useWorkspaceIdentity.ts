import { useAtomValue } from "jotai";
import type { LucideIcon } from "lucide-react";
import { GitBranchIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { workspaceIdentitySourcesAtomFamily } from "../atoms/workspaceIdentity.ts";

// How long to wait for a current branch before labelling a workspace with its
// requested branch name. The current branch normally streams in well under
// this, but the branch poller publishes one only for a workspace whose working
// directory resolves: a workspace whose environment was never created, or whose
// worktree is gone, never gets one. Waiting first avoids flashing a requested
// name that an agent has since renamed.
export const IDENTITY_LABEL_GRACE_MS = 2000;

/**
 * What the UI calls a workspace's checkout. `LOADING` is a short wait for the
 * current branch; `UNAVAILABLE` means nothing is known, and surfaces render no
 * label at all.
 */
export type WorkspaceIdentityLabel =
  | { status: "LOADING" }
  | { status: "UNAVAILABLE" }
  | { status: "READY"; text: string; copyText: string; icon: LucideIcon };

const branchLabel = (branch: string): WorkspaceIdentityLabel => ({
  status: "READY",
  text: branch,
  copyText: branch,
  icon: GitBranchIcon,
});

/**
 * Resolve a workspace's identity label. The current branch wins, from the
 * stream or else from a REST read of the same scan cache. Only once the grace
 * window has passed does the requested branch name stand in. The source branch
 * never does: it is the base the workspace was created from, not its own branch.
 */
export const resolveWorkspaceIdentityLabel = (sources: {
  liveBranch: string | null;
  fetchedBranch: string | null;
  requestedBranchName: string | null;
  hasGraceElapsed: boolean;
}): WorkspaceIdentityLabel => {
  const currentBranch = sources.liveBranch ?? sources.fetchedBranch;
  if (currentBranch !== null) {
    return branchLabel(currentBranch);
  }

  if (!sources.hasGraceElapsed) {
    return { status: "LOADING" };
  }
  return sources.requestedBranchName !== null ? branchLabel(sources.requestedBranchName) : { status: "UNAVAILABLE" };
};

/**
 * The identity label of a workspace, for every surface that names one. Pass
 * `fetchedBranch` when the caller holds a REST response carrying the workspace's
 * current branch.
 */
export const useWorkspaceIdentityLabel = ({
  workspaceId,
  fetchedBranch,
}: {
  workspaceId: string;
  fetchedBranch?: string | null;
}): WorkspaceIdentityLabel => {
  const { liveBranch, requestedBranchName } = useAtomValue(workspaceIdentitySourcesAtomFamily(workspaceId));
  // Keyed by workspace so a surface that switches workspaces waits afresh.
  const [graceElapsedWorkspaceId, setGraceElapsedWorkspaceId] = useState<string | null>(null);
  const isCurrentBranchKnown = liveBranch !== null || (fetchedBranch ?? null) !== null;

  useEffect(() => {
    if (isCurrentBranchKnown) {
      return undefined;
    }
    const timer = setTimeout((): void => setGraceElapsedWorkspaceId(workspaceId), IDENTITY_LABEL_GRACE_MS);
    return (): void => clearTimeout(timer);
  }, [workspaceId, isCurrentBranchKnown]);

  return resolveWorkspaceIdentityLabel({
    liveBranch,
    fetchedBranch: fetchedBranch ?? null,
    requestedBranchName,
    hasGraceElapsed: graceElapsedWorkspaceId === workspaceId,
  });
};
