import { useAtomValue } from "jotai";
import { useMemo } from "react";

import type { WorkspaceBranchInfo } from "../../../api";
import { workspaceBranchAtomFamily } from "../atoms/workspaceBranch.ts";

/**
 * Hook to get the current branch for a workspace's working directory.
 *
 * Branch info is pushed from the backend via the WebSocket stream,
 * so this hook is a simple atom reader with no polling.
 *
 * @param workspaceId - The workspace ID
 * @returns The current branch info, or null if not available
 */
export const useWorkspaceBranch = (workspaceId: string | null | undefined): WorkspaceBranchInfo | null => {
  const branchAtom = useMemo(() => workspaceBranchAtomFamily(workspaceId ?? ""), [workspaceId]);
  const branchInfo = useAtomValue(branchAtom);
  if (!workspaceId) return null;
  return branchInfo;
};
