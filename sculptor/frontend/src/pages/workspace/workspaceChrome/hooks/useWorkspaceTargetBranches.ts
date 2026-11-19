import { useAtomValue } from "jotai";
import { useMemo } from "react";

import { workspaceTargetBranchesAtomFamily } from "~/common/state/atoms/workspaceTargetBranches";

const NO_PR_BASE_NAMES: Readonly<Record<string, string>> = {};

/**
 * Return the branches a workspace can target as its merge/diff base, with the
 * base branch a pull request from each would name.
 *
 * For git these are the repo's remote-tracking branches, or its local branches
 * when the repo has no remote, so the selector is never empty; for jj they are
 * bookmark symbols such as `main@origin`. Data flows over the unified WebSocket
 * stream from the backend's pollers, so the list stays current as refs change in
 * the workspace (e.g. after `git fetch`). Both are empty until the first poll
 * tick reaches the frontend.
 */
export const useWorkspaceTargetBranches = (
  workspaceId: string,
): { targetBranches: Array<string>; prBaseNames: Readonly<Record<string, string>> } => {
  const targetBranchesAtom = useMemo(() => workspaceTargetBranchesAtomFamily(workspaceId), [workspaceId]);
  const info = useAtomValue(targetBranchesAtom);
  return useMemo(
    () => ({ targetBranches: info?.targetBranches ?? [], prBaseNames: info?.prBaseNames ?? NO_PR_BASE_NAMES }),
    [info],
  );
};
