import { existsSync } from "node:fs";

import { getOrm } from "~/db/orm";
import { getRepo, getWorkspace, listRecentWorkspaces } from "~/db/repositories";
import type { WorkspaceRow } from "~/db/schema";
import { workingDirectory } from "~/environment/paths";
import { eventBus } from "~/events";
import type { BusEvent } from "~/events/types";
import { runGit } from "~/git";
import { localPathFromRepo } from "~/services/project";

// Repo-polling manager (web/repo_polling_manager.py). Refreshes each open
// workspace's local branch + remote-branch info on a fixed 3 s cadence and
// emits the events that feed
// workspace_branch_by_workspace_id / workspace_remote_branches_by_workspace_id.
// A workspace whose checkout has been torn down stops being polled (avoids the
// tight-loop-on-removed-repo hang).

export const WORKSPACE_BRANCH_POLL_SECONDS = 3;
export const WORKSPACE_REMOTE_BRANCHES_POLL_SECONDS = 3;

export interface RepoPollingDeps {
  workingDirForWorkspace: (workspace: WorkspaceRow) => string | null;
  intervalMs: number;
}

function defaultWorkingDir(workspace: WorkspaceRow): string | null {
  if (workspace.environmentId === null) {
    return null;
  }
  const repo = getRepo(getOrm(), workspace.projectId);
  const repoHostPath =
    repo !== undefined ? (localPathFromRepo(repo) ?? undefined) : undefined;
  return workingDirectory(
    workspace.environmentId,
    workspace.initializationStrategy,
    repoHostPath,
  );
}

export class RepoPollingManager {
  private readonly deps: RepoPollingDeps;
  private readonly timers = new Map<string, ReturnType<typeof setInterval>>();
  private running = false;
  private unsubscribe: (() => void) | undefined;

  constructor(deps: Partial<RepoPollingDeps> = {}) {
    this.deps = {
      workingDirForWorkspace: deps.workingDirForWorkspace ?? defaultWorkingDir,
      intervalMs: deps.intervalMs ?? WORKSPACE_BRANCH_POLL_SECONDS * 1000,
    };
  }

  // Poll one workspace: read the current branch + remote branches and emit the
  // events. Returns false when the checkout is gone (caller stops polling it).
  async pollWorkspace(workspace: WorkspaceRow): Promise<boolean> {
    const cwd = this.deps.workingDirForWorkspace(workspace);
    if (cwd === null || !existsSync(cwd)) {
      return false;
    }
    const branchResult = await runGit(
      ["rev-parse", "--abbrev-ref", "HEAD"],
      cwd,
    ).catch(() => null);
    if (branchResult !== null && branchResult.exitCode === 0) {
      const currentBranch = branchResult.stdout.trim();
      eventBus.publish({
        kind: "workspace_branch",
        workspaceId: workspace.objectId,
        projectId: workspace.projectId,
        status: {
          workspace_id: workspace.objectId,
          current_branch: currentBranch,
        },
      });
    }
    const remoteResult = await runGit(
      ["branch", "-r", "--format=%(refname:short)"],
      cwd,
    ).catch(() => null);
    if (remoteResult !== null && remoteResult.exitCode === 0) {
      const remoteBranches = remoteResult.stdout
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line !== "" && !line.includes("->"));
      eventBus.publish({
        kind: "workspace_remote_branches",
        workspaceId: workspace.objectId,
        projectId: workspace.projectId,
        status: {
          workspace_id: workspace.objectId,
          remote_branches: remoteBranches,
        },
      });
    }
    return true;
  }

  private startWorkspace(workspace: WorkspaceRow): void {
    if (this.timers.has(workspace.objectId)) {
      return;
    }
    const timer = setInterval(() => {
      void this.pollWorkspace(workspace).then((alive) => {
        if (!alive) {
          this.stopWorkspace(workspace.objectId);
        }
      });
    }, this.deps.intervalMs);
    if (typeof timer.unref === "function") {
      timer.unref();
    }
    this.timers.set(workspace.objectId, timer);
  }

  private stopWorkspace(workspaceId: string): void {
    const timer = this.timers.get(workspaceId);
    if (timer !== undefined) {
      clearInterval(timer);
      this.timers.delete(workspaceId);
    }
  }

  start(): void {
    if (this.running) {
      return;
    }
    this.running = true;
    for (const workspace of listRecentWorkspaces(getOrm()).filter(
      (workspace) => !workspace.isDeleted && workspace.isOpen,
    )) {
      this.startWorkspace(workspace);
    }
    // Workspaces created after boot (the common case — the backend starts with
    // none) must also be polled, so pick them up from their data_model_change.
    this.unsubscribe = eventBus.subscribe((event: BusEvent) => {
      if (event.kind !== "data_model_change") {
        return;
      }
      for (const ref of event.changedEntities ?? []) {
        if (ref.type !== "workspace") {
          continue;
        }
        const workspace = getWorkspace(getOrm(), ref.id);
        if (workspace !== undefined && !workspace.isDeleted && workspace.isOpen) {
          this.startWorkspace(workspace);
        } else {
          this.stopWorkspace(ref.id);
        }
      }
    });
  }

  stop(): void {
    this.running = false;
    this.unsubscribe?.();
    this.unsubscribe = undefined;
    for (const timer of this.timers.values()) {
      clearInterval(timer);
    }
    this.timers.clear();
  }

  get polledWorkspaceCount(): number {
    return this.timers.size;
  }
}

let singleton: RepoPollingManager | undefined;

export function getRepoPollingManager(): RepoPollingManager {
  if (singleton === undefined) {
    singleton = new RepoPollingManager();
  }
  return singleton;
}

export function resetRepoPollingManagerForTests(): void {
  singleton?.stop();
  singleton = undefined;
}
