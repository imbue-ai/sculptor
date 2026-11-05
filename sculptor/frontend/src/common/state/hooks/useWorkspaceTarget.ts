import { useWorkspace } from "./useWorkspace.ts";

/**
 * The ref a workspace diffs against and opens pull requests into, or null when
 * Sculptor found no default branch while creating the workspace.
 */
export const useWorkspaceTarget = (workspaceId: string): string | null =>
  useWorkspace(workspaceId)?.targetBranch ?? null;
