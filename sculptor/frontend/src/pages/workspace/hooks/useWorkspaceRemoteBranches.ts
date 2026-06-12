import { useAtomValue } from "jotai";
import { useMemo } from "react";

import { workspaceRemoteBranchesAtomFamily } from "~/common/state/atoms/workspaceRemoteBranches";

/**
 * Return the remote-tracking branches available in a workspace's repository.
 *
 * Data flows over the unified WebSocket stream from the backend's workspace
 * branch polling manager, so the list stays current as refs change in the
 * workspace (e.g. after `git fetch`). Returns an empty array until the first
 * poll tick reaches the frontend.
 */
export const useWorkspaceRemoteBranches = (workspaceId: string): Array<string> => {
  const remoteBranchesAtom = useMemo(() => workspaceRemoteBranchesAtomFamily(workspaceId), [workspaceId]);
  const info = useAtomValue(remoteBranchesAtom);
  return info?.remoteBranches ?? [];
};
