import { mkdir } from "node:fs/promises";

import type { WorkspaceInitializationStrategy } from "~/db/schema";
import { workingDirectory } from "~/environment/paths";
import { addWorktree, cloneShared, createBranch, revParseHead } from "~/git/git";

export interface SetupWorkspaceParams {
  // The workspace root (the absolute workspaces/<id> path; becomes environment_id).
  root: string;
  strategy: WorkspaceInitializationStrategy;
  // The user's repository working directory.
  repoHostPath: string;
  // Base ref the new branch / clone checkout starts from.
  sourceBranch?: string | null;
  // The new branch name (required for WORKTREE; optional for CLONE; null IN_PLACE).
  requestedBranchName?: string | null;
}

export interface SetupWorkspaceResult {
  workingDirectory: string;
  sourceGitHash: string;
}

// Builds a workspace's working tree per its initialization strategy, then
// captures source_git_hash (the diff base). The working-dir layout
// matches the Python LocalEnvironment (workspaces/<id>/code for worktree/clone,
// the user's repo for in-place) — the migration preserves these paths.
export async function setupWorkspace(params: SetupWorkspaceParams): Promise<SetupWorkspaceResult> {
  const workDir = workingDirectory(params.root, params.strategy, params.repoHostPath);

  if (params.strategy === "WORKTREE") {
    if (params.sourceBranch === undefined || params.sourceBranch === null) {
      throw new Error("sourceBranch (base ref) is required for WORKTREE initialization");
    }
    if (params.requestedBranchName === undefined || params.requestedBranchName === null) {
      throw new Error("requestedBranchName is required for WORKTREE initialization");
    }
    await mkdir(params.root, { recursive: true });
    await addWorktree(params.repoHostPath, workDir, params.requestedBranchName, params.sourceBranch);
  } else if (params.strategy === "CLONE") {
    await mkdir(params.root, { recursive: true });
    await cloneShared(params.repoHostPath, workDir, params.sourceBranch ?? undefined);
    if (params.requestedBranchName !== undefined && params.requestedBranchName !== null && params.requestedBranchName.trim() !== "") {
      await createBranch(workDir, params.requestedBranchName);
    }
  }
  // IN_PLACE: the agent works directly in the user's repo; no tree to build.

  return { workingDirectory: workDir, sourceGitHash: await revParseHead(workDir) };
}
