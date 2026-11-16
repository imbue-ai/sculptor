import { useAtomValue } from "jotai";
import type { LucideIcon } from "lucide-react";
import { BookmarkIcon, GitBranchIcon, GitCommitVerticalIcon } from "lucide-react";
import { useEffect, useState } from "react";

import type { WorkspaceJjStateInfo } from "../../../api";
import { shortChangeId } from "../../utils/jjChangeId.ts";
import type { WorkspaceIdentitySources } from "../atoms/workspaceIdentity.ts";
import { workspaceIdentitySourcesAtomFamily } from "../atoms/workspaceIdentity.ts";

// How long to wait for a current branch, or a jj workspace's state, before
// falling back to the requested name. Waiting avoids flashing a name an agent
// has since renamed. The wait is bounded because the pollers never report on a
// workspace without a working directory (no environment yet, or checkout gone).
export const IDENTITY_LABEL_GRACE_MS = 2000;

/**
 * What the UI calls a workspace's checkout. `LOADING` is a short wait for the
 * current branch; `UNAVAILABLE` means nothing is known, and surfaces render no
 * label at all. A tentative label names what the workspace will be called but
 * is not yet: a jj workspace's requested bookmark before it exists.
 */
export type WorkspaceIdentityLabel =
  | { status: "LOADING" }
  | { status: "UNAVAILABLE" }
  | { status: "READY"; text: string; copyText: string; icon: LucideIcon; isTentative: boolean };

const branchLabel = (branch: string): WorkspaceIdentityLabel => ({
  status: "READY",
  text: branch,
  copyText: branch,
  icon: GitBranchIcon,
  isTentative: false,
});

const requestedBookmarkLabel = (requestedBookmark: string, copyText: string): WorkspaceIdentityLabel => ({
  status: "READY",
  text: requestedBookmark,
  copyText,
  icon: BookmarkIcon,
  isTentative: true,
});

// A jj workspace is named by its primary bookmark. Until it has one, the
// requested bookmark stands in, and copying gives the change id, which already
// names the work.
const jjStateLabel = (jjState: WorkspaceJjStateInfo, requestedBookmark: string | null): WorkspaceIdentityLabel => {
  if (jjState.primaryBookmark !== null) {
    return {
      status: "READY",
      text: jjState.primaryBookmark,
      copyText: jjState.primaryBookmark,
      icon: BookmarkIcon,
      isTentative: false,
    };
  }

  if (requestedBookmark !== null) {
    return requestedBookmarkLabel(requestedBookmark, jjState.workingCopyChangeId);
  }
  const { uniquePrefix, rest } = shortChangeId({
    changeId: jjState.workingCopyChangeId,
    uniquePrefixLength: jjState.workingCopyChangeIdPrefixLength,
  });
  return {
    status: "READY",
    text: `${uniquePrefix}${rest}`,
    copyText: jjState.workingCopyChangeId,
    icon: GitCommitVerticalIcon,
    isTentative: false,
  };
};

/**
 * Resolve a workspace's identity label. A fetched branch is the same scan-cache
 * value as the live one, read over REST; jj workspaces have none. Never fall
 * back to the source branch: it is the base the workspace was created from, not
 * its own branch.
 */
export const resolveWorkspaceIdentityLabel = (inputs: {
  sources: WorkspaceIdentitySources;
  fetchedBranch: string | null;
  hasGraceElapsed: boolean;
}): WorkspaceIdentityLabel => {
  const { sources, hasGraceElapsed } = inputs;
  if (sources.vcs === "jj") {
    if (sources.jjState !== null) {
      return jjStateLabel(sources.jjState, sources.requestedBranchName);
    }

    if (!hasGraceElapsed) {
      return { status: "LOADING" };
    }
    return sources.requestedBranchName !== null
      ? requestedBookmarkLabel(sources.requestedBranchName, sources.requestedBranchName)
      : { status: "UNAVAILABLE" };
  }

  const currentBranch = sources.liveBranch ?? inputs.fetchedBranch;
  if (currentBranch !== null) {
    return branchLabel(currentBranch);
  }

  if (!hasGraceElapsed) {
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
  const sources = useAtomValue(workspaceIdentitySourcesAtomFamily(workspaceId));
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
    sources,
    fetchedBranch: fetchedBranch ?? null,
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
