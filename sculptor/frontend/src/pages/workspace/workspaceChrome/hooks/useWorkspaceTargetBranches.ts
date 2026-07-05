import { useAtomValue } from "jotai";
import { useMemo } from "react";

import { workspaceTargetBranchesAtomFamily } from "~/common/state/atoms/workspaceTargetBranches";

/**
 * Return the branches a workspace can target as its merge/diff base.
 *
 * These are the repo's remote-tracking branches, or its local branches when the
 * repo has no remote, so the selector is never empty. Data flows over the
 * unified WebSocket stream from the backend's workspace branch polling manager,
 * so the list stays current as refs change in the workspace (e.g. after
 * `git fetch`). Returns an empty array until the first poll tick reaches the
 * frontend.
 */
export const useWorkspaceTargetBranches = (workspaceId: string): Array<string> => {
  const targetBranchesAtom = useMemo(() => workspaceTargetBranchesAtomFamily(workspaceId), [workspaceId]);
  const info = useAtomValue(targetBranchesAtom);
  return info?.targetBranches ?? [];
};
