import { toRemoteRefName } from "../../utils/refNames.ts";
import { useWorkspace } from "./useWorkspace.ts";

/** The ref a workspace diffs against and opens pull requests into. */
export const useWorkspaceTarget = (workspaceId: string): string => {
  const targetBranch = useWorkspace(workspaceId)?.targetBranch;
  return targetBranch ?? toRemoteRefName("main");
};
