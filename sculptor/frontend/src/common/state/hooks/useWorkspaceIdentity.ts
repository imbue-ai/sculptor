import { useAtomValue } from "jotai";
import type { LucideIcon } from "lucide-react";
import { GitBranchIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { workspaceIdentitySourcesAtomFamily } from "../atoms/workspaceIdentity.ts";

// How long to wait for a current branch before falling back to the requested
// branch name. Waiting avoids flashing a name an agent has since renamed. The
// wait is bounded because the branch poller never reports a branch for a
// workspace without a working directory (no environment yet, or worktree gone).
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
 * Resolve a workspace's identity label. A fetched branch is the same scan-cache
 * value as the live one, read over REST. Never fall back to the source branch:
 * it is the base the workspace was created from, not its own branch.
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
  // The workspace the grace window is running for. Moving to another workspace
  // restarts it, so a reused surface waits afresh on every switch.
  const [graceWindow, setGraceWindow] = useState<{ workspaceId: string; hasElapsed: boolean }>({
    workspaceId,
    hasElapsed: false,
  });
  if (graceWindow.workspaceId !== workspaceId) {
    setGraceWindow({ workspaceId, hasElapsed: false });
  }
  const label = resolveWorkspaceIdentityLabel({
    liveBranch,
    fetchedBranch: fetchedBranch ?? null,
    requestedBranchName,
    hasGraceElapsed: graceWindow.hasElapsed,
  });
  const isLoading = label.status === "LOADING";

  useEffect(() => {
    if (!isLoading) {
      return undefined;
    }
    const timer = setTimeout((): void => setGraceWindow({ workspaceId, hasElapsed: true }), IDENTITY_LABEL_GRACE_MS);
    return (): void => clearTimeout(timer);
  }, [workspaceId, isLoading]);

  return label;
};
