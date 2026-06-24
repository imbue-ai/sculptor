import path from "node:path";

import { getWorkspacesFolder } from "~/config/sculptor_folder";
import type { WorkspaceInitializationStrategy } from "~/db/schema";

// On-disk workspace layout, mirroring interfaces/environments/base.py +
// LocalEnvironment. MUST match the Python layout exactly — the one-time
// migration (Task 8.1) preserves these directories and ids, so a different
// scheme would orphan existing workspaces and break Claude/Pi session-file
// resolution. The workspace root is the absolute path stored as the workspace's
// environment_id (a `workspaces/<uuid-hex>` directory).
export const CODE_SUBDIR = "code";
export const STATE_DIR = "state";
export const ARTIFACTS_DIR = "artifacts";
export const ATTACHMENTS_DIR = "attachments";
export const TASKS_SUBDIR = "tasks";

// The root path for a freshly-created workspace directory, named by a uuid hex
// segment (the new environment_id is the string form of this path).
export function newWorkspaceRootPath(workspaceDirId: string, env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getWorkspacesFolder(env), workspaceDirId);
}

export function workingDirectory(
  root: string,
  strategy: WorkspaceInitializationStrategy,
  repoHostPath: string | undefined,
): string {
  if (strategy === "CLONE" || strategy === "WORKTREE") {
    return path.join(root, CODE_SUBDIR);
  }
  if (repoHostPath === undefined) {
    throw new Error("repoHostPath is required for an IN_PLACE workspace");
  }
  return repoHostPath;
}

export function statePath(root: string, agentId: string): string {
  return path.join(root, STATE_DIR, TASKS_SUBDIR, agentId);
}

export function artifactsPath(root: string, agentId: string): string {
  return path.join(root, ARTIFACTS_DIR, TASKS_SUBDIR, agentId);
}

export function attachmentsPath(root: string): string {
  return path.join(root, ATTACHMENTS_DIR);
}
