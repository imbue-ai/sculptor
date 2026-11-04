import { useAtomValue } from "jotai";

import { prDefaultTargetBranchAtom } from "../atoms/userConfig.ts";
import { useWorkspace } from "./useWorkspace.ts";

/**
 * The ref a workspace diffs against and opens pull requests into: its own
 * target, or the default target setting when it has none.
 */
export const useWorkspaceTarget = (workspaceId: string): string => {
  const targetBranch = useWorkspace(workspaceId)?.targetBranch;
  const defaultTargetBranch = useAtomValue(prDefaultTargetBranchAtom);
  return targetBranch ?? defaultTargetBranch;
};
