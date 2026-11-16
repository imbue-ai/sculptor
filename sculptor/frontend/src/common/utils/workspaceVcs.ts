import type { Workspace } from "~/api";
import { WorkspaceInitializationStrategy } from "~/api";

/** The version control a workspace's checkout uses. A jj workspace has no git inside it. */
export type WorkspaceVcs = "git" | "jj";

const VCS_BY_STRATEGY: Readonly<Record<WorkspaceInitializationStrategy, WorkspaceVcs>> = {
  [WorkspaceInitializationStrategy.IN_PLACE]: "git",
  [WorkspaceInitializationStrategy.CLONE]: "git",
  [WorkspaceInitializationStrategy.WORKTREE]: "git",
  [WorkspaceInitializationStrategy.JJ_WORKSPACE]: "jj",
};

/** Tell a workspace's version control from its creation mode, which never changes. */
export const workspaceVcsOf = (workspace: Pick<Workspace, "initializationStrategy">): WorkspaceVcs =>
  VCS_BY_STRATEGY[workspace.initializationStrategy];
