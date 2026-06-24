import { randomUUID } from "node:crypto";
import { rmSync } from "node:fs";
import path from "node:path";

import { getOrm } from "~/db/orm";
import {
  createWorkspace,
  getRepo,
  getWorkspace,
  listAgentsByWorkspace,
  listRecentWorkspaces,
  listWorkspacesByRepo,
  softDeleteAgent,
  softDeleteWorkspace,
  updateWorkspace,
} from "~/db/repositories";
import {
  CODE_SUBDIR,
  newWorkspaceRootPath,
  statePath,
} from "~/environment/paths";
import { eventBus } from "~/events";
import { previewBranchName, runGit, setupWorkspace } from "~/git";
import { newWorkspaceId } from "~/ids";
import type {
  WorkspaceRow,
  WorkspaceInitializationStrategy,
} from "~/db/schema";
import { localPathFromRepo } from "~/services/project";
import {
  resolveWorkspaceSetupCommand,
  WorkspaceSetupRunner,
  type SetupStatus,
} from "~/services/workspace_setup";

// Workspace lifecycle service (web/app.py workspace handlers +
// services/workspace_service/). Create builds the working tree (Task 3.2),
// resolves the diff target branch, and kicks off the setup-command runner; the
// wire keeps the camelCase Workspace shapes (RW-API-3).

export class WorkspaceError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

// --- wire shapes ------------------------------------------------------------

export interface WorkspaceSetupSnapshotWire {
  status: SetupStatus;
  runId: string | null;
  exitCode: number | null;
  startedAt: number | null;
  finishedAt: number | null;
  logTruncated: boolean;
}

export interface WorkspaceResponseWire {
  objectId: string;
  projectId: string;
  description: string;
  initializationStrategy: WorkspaceInitializationStrategy;
  sourceBranch: string | null;
  targetBranch: string | null;
  requestedBranchName: string | null;
  environmentId: string | null;
  isDeleted: boolean;
  isOpen: boolean;
  createdAt: string;
  workspaceSetupCommand: string | null;
  setup: WorkspaceSetupSnapshotWire | null;
}

function rowSetupSnapshot(row: WorkspaceRow): WorkspaceSetupSnapshotWire {
  return {
    status: row.setupStatus as SetupStatus,
    runId: row.setupRunId ?? null,
    exitCode: row.setupExitCode ?? null,
    startedAt: row.setupStartedAt ?? null,
    finishedAt: row.setupFinishedAt ?? null,
    logTruncated: row.setupLogTruncated,
  };
}

export function workspaceRowToResponse(
  row: WorkspaceRow,
): WorkspaceResponseWire {
  return {
    objectId: row.objectId,
    projectId: row.projectId,
    description: row.description,
    initializationStrategy: row.initializationStrategy,
    sourceBranch: row.sourceBranch ?? null,
    targetBranch: row.targetBranch ?? null,
    requestedBranchName: row.requestedBranchName ?? null,
    environmentId: row.environmentId ?? null,
    isDeleted: row.isDeleted,
    isOpen: row.isOpen,
    createdAt: row.createdAt,
    workspaceSetupCommand: row.setupCommand ?? null,
    setup: rowSetupSnapshot(row),
  };
}

export interface RecentWorkspaceWire {
  objectId: string;
  projectId: string;
  description: string;
  initializationStrategy: WorkspaceInitializationStrategy;
  sourceBranch: string | null;
  isDeleted: boolean;
  createdAt: string;
  projectName: string;
  agentCount: number;
  isOpen: boolean;
  lastActivityAt: string | null;
}

// --- default target branch (default_implementation _resolve_default_target_branch) ---

async function detectDefaultBranchForRemote(
  repoPath: string,
  remote: string,
): Promise<string | null> {
  const symbolic = await runGit(
    ["symbolic-ref", `refs/remotes/${remote}/HEAD`],
    repoPath,
  );
  if (symbolic.exitCode === 0 && symbolic.stdout.trim() !== "") {
    const ref = symbolic.stdout.trim();
    return ref.startsWith("refs/remotes/")
      ? ref.slice("refs/remotes/".length)
      : ref;
  }
  for (const branch of ["main", "master"]) {
    const candidate = `${remote}/${branch}`;
    const verify = await runGit(
      ["rev-parse", "--verify", `refs/remotes/${candidate}`],
      repoPath,
    );
    if (verify.exitCode === 0) {
      return candidate;
    }
  }
  return null;
}

async function detectLocalMainOrMaster(
  repoPath: string,
): Promise<string | null> {
  for (const branch of ["main", "master"]) {
    const verify = await runGit(
      ["rev-parse", "--verify", `refs/heads/${branch}`],
      repoPath,
    );
    if (verify.exitCode === 0) {
      return branch;
    }
  }
  return null;
}

async function resolveDefaultTargetBranch(
  repoPath: string,
): Promise<string | null> {
  const remote = await detectDefaultBranchForRemote(repoPath, "origin");
  if (remote !== null) {
    return remote;
  }
  return detectLocalMainOrMaster(repoPath);
}

// --- the service ------------------------------------------------------------

export interface CreateWorkspaceInput {
  projectId: string;
  initializationStrategy: WorkspaceInitializationStrategy;
  sourceBranch?: string | null;
  description?: string | null;
  requestedBranchName?: string | null;
  targetBranch?: string | null;
}

export class WorkspaceService {
  readonly setupRunner = new WorkspaceSetupRunner({
    persist: (workspaceId, snapshot, command) => {
      updateWorkspace(getOrm(), workspaceId, {
        setupStatus: snapshot.status,
        setupRunId: snapshot.runId,
        setupExitCode: snapshot.exitCode,
        setupStartedAt: snapshot.startedAt,
        setupFinishedAt: snapshot.finishedAt,
        setupLogTruncated: snapshot.logTruncated,
        setupCommand: command,
        setupLogPath: "setup_log.txt",
      });
    },
    newRunId: () => randomUUID(),
    now: () => Date.now() / 1000,
  });

  private setupStateDir(workspaceId: string, environmentId: string): string {
    // The setup log lives in the workspace's per-agent state root; reuse the
    // workspace root's state dir keyed by the workspace id.
    return statePath(environmentId, workspaceId);
  }

  async create(input: CreateWorkspaceInput): Promise<WorkspaceResponseWire> {
    const orm = getOrm();
    const repo = getRepo(orm, input.projectId);
    if (repo === undefined || repo.isDeleted) {
      throw new WorkspaceError(404, "Project not found");
    }
    const strategy = input.initializationStrategy;
    const requested = input.requestedBranchName ?? null;

    if (strategy === "IN_PLACE" && requested !== null && requested !== "") {
      throw new WorkspaceError(
        422,
        "in_place workspaces cannot have a branch name",
      );
    }
    if (strategy === "WORKTREE") {
      if (requested === null || requested.trim() === "") {
        throw new WorkspaceError(
          400,
          "A branch name is required for worktree workspaces",
        );
      }
      if (input.sourceBranch === null || input.sourceBranch === undefined) {
        throw new WorkspaceError(
          400,
          "A source branch is required for worktree workspaces",
        );
      }
    }

    const repoHostPath = localPathFromRepo(repo);
    if (repoHostPath === null) {
      throw new WorkspaceError(400, "Project path is not accessible");
    }

    // Reject a branch name that already exists (any strategy that names one).
    if (requested !== null && requested.trim() !== "") {
      const exists = await runGit(
        ["rev-parse", "--verify", "--quiet", `refs/heads/${requested.trim()}`],
        repoHostPath,
      );
      if (exists.exitCode === 0) {
        throw new WorkspaceError(409, `Branch already exists: ${requested}`);
      }
    }

    const workspaceId = newWorkspaceId();
    const root = newWorkspaceRootPath(workspaceId);
    const setup = await setupWorkspace({
      root,
      strategy,
      repoHostPath,
      sourceBranch: input.sourceBranch ?? null,
      requestedBranchName: requested,
    });

    const targetBranch =
      input.targetBranch ?? (await resolveDefaultTargetBranch(repoHostPath));
    const command = resolveWorkspaceSetupCommand(
      repo.workspaceSetupCommand ?? null,
    );
    const hasCommand = command !== null;
    const initialStatus: SetupStatus =
      hasCommand && strategy !== "IN_PLACE" ? "pending" : "not_configured";

    const row = createWorkspace(orm, {
      objectId: workspaceId,
      projectId: input.projectId,
      description: input.description ?? "",
      initializationStrategy: strategy,
      sourceBranch: input.sourceBranch ?? null,
      targetBranch,
      requestedBranchName: requested,
      environmentId: root,
      sourceGitHash: setup.sourceGitHash,
      setupStatus: initialStatus,
      setupCommand: command,
    });
    publishWorkspaceChanged(workspaceId);

    // Kick off the setup command (the runner transitions pending -> running ->
    // succeeded/failed and persists each step).
    if (initialStatus === "pending" && command !== null) {
      this.setupRunner.start(
        workspaceId,
        path.join(root, CODE_SUBDIR),
        command,
        this.setupStateDir(workspaceId, root),
      );
    } else {
      this.emitSetupStatus(workspaceId, rowSetupSnapshot(row));
    }
    const current = getWorkspace(orm, workspaceId) ?? row;
    return workspaceRowToResponse(current);
  }

  get(workspaceId: string): WorkspaceResponseWire {
    const row = getWorkspace(getOrm(), workspaceId);
    if (row === undefined || row.isDeleted) {
      throw new WorkspaceError(404, "Workspace not found");
    }
    return workspaceRowToResponse(row);
  }

  listByProject(projectId: string): WorkspaceResponseWire[] {
    return listWorkspacesByRepo(getOrm(), projectId)
      .filter((row) => !row.isDeleted)
      .map(workspaceRowToResponse);
  }

  recent(): RecentWorkspaceWire[] {
    const orm = getOrm();
    return listRecentWorkspaces(orm)
      .filter((row) => !row.isDeleted)
      .map((row) => {
        const repo = getRepo(orm, row.projectId);
        const agents = listAgentsByWorkspace(orm, row.objectId).filter(
          (a) => !a.isDeleted,
        );
        const lastAgent = agents.reduce<string | null>(
          (latest, agent) =>
            latest === null || agent.createdAt > latest
              ? agent.createdAt
              : latest,
          null,
        );
        return {
          objectId: row.objectId,
          projectId: row.projectId,
          description: row.description,
          initializationStrategy: row.initializationStrategy,
          sourceBranch: row.sourceBranch ?? null,
          isDeleted: row.isDeleted,
          createdAt: row.createdAt,
          projectName: repo?.name ?? "",
          agentCount: agents.length,
          isOpen: row.isOpen,
          lastActivityAt: lastAgent ?? row.createdAt,
        };
      });
  }

  batchUpdateOpenState(workspaceIds: string[], isOpen: boolean): void {
    const orm = getOrm();
    for (const id of workspaceIds) {
      const row = getWorkspace(orm, id);
      if (row !== undefined && !row.isDeleted) {
        updateWorkspace(orm, id, { isOpen });
        publishWorkspaceChanged(id);
      }
    }
  }

  delete(workspaceId: string): void {
    const orm = getOrm();
    const row = getWorkspace(orm, workspaceId);
    if (row === undefined || row.isDeleted) {
      throw new WorkspaceError(404, "Workspace not found");
    }
    // Tear down the environment before soft-deleting: cancel any setup, remove
    // the worktree, drop the workspace dir.
    this.setupRunner.cancel(workspaceId);
    if (row.environmentId !== null) {
      if (row.initializationStrategy === "WORKTREE") {
        const repo = getRepo(orm, row.projectId);
        const repoHostPath =
          repo !== undefined ? localPathFromRepo(repo) : null;
        if (repoHostPath !== null) {
          void runGit(
            [
              "worktree",
              "remove",
              "--force",
              path.join(row.environmentId, CODE_SUBDIR),
            ],
            repoHostPath,
          );
        }
      }
      rmSync(row.environmentId, { recursive: true, force: true });
    }
    for (const agent of listAgentsByWorkspace(orm, workspaceId)) {
      softDeleteAgent(orm, agent.objectId);
    }
    softDeleteWorkspace(orm, workspaceId);
    publishWorkspaceChanged(workspaceId);
  }

  cancelSetup(workspaceId: string): WorkspaceSetupSnapshotWire {
    const row = getWorkspace(getOrm(), workspaceId);
    if (row === undefined || row.isDeleted) {
      throw new WorkspaceError(404, "Workspace not found");
    }
    const snapshot = this.setupRunner.cancel(workspaceId);
    if (snapshot === null) {
      throw new WorkspaceError(409, "Setup is not running");
    }
    return snapshot;
  }

  rerunSetup(workspaceId: string): WorkspaceSetupSnapshotWire {
    const orm = getOrm();
    const row = getWorkspace(orm, workspaceId);
    if (row === undefined || row.isDeleted) {
      throw new WorkspaceError(404, "Workspace not found");
    }
    if (row.environmentId === null) {
      throw new WorkspaceError(409, "Workspace environment is not ready");
    }
    if (this.setupRunner.isRunning(workspaceId)) {
      throw new WorkspaceError(409, "Setup is already running");
    }
    const repo = getRepo(orm, row.projectId);
    const command = resolveWorkspaceSetupCommand(
      repo?.workspaceSetupCommand ?? null,
    );
    if (command === null) {
      throw new WorkspaceError(422, "No setup command configured");
    }
    return this.setupRunner.start(
      workspaceId,
      path.join(row.environmentId, CODE_SUBDIR),
      command,
      this.setupStateDir(workspaceId, row.environmentId),
    );
  }

  private emitSetupStatus(
    workspaceId: string,
    snapshot: WorkspaceSetupSnapshotWire,
  ): void {
    eventBus.publish({
      kind: "workspace_setup_status",
      workspaceId,
      status: {
        workspaceId,
        status: snapshot.status,
        runId: snapshot.runId,
        exitCode: snapshot.exitCode,
        startedAt: snapshot.startedAt,
        finishedAt: snapshot.finishedAt,
        logTruncated: snapshot.logTruncated,
      },
    });
  }
}

export async function previewWorkspaceBranchName(
  projectId: string,
  workspaceName: string,
  strategy: WorkspaceInitializationStrategy,
): Promise<string> {
  const orm = getOrm();
  const repo = getRepo(orm, projectId);
  if (repo === undefined) {
    throw new WorkspaceError(404, "Project not found");
  }
  const repoHostPath = localPathFromRepo(repo);
  if (repoHostPath === null) {
    return "";
  }
  return previewBranchName({
    strategy,
    repoHostPath,
    workspaceName,
    namingPattern: repo.namingPattern ?? null,
  });
}

function publishWorkspaceChanged(workspaceId: string): void {
  eventBus.publish({
    kind: "data_model_change",
    changedEntities: [{ type: "workspace", id: workspaceId }],
  });
}

let singleton: WorkspaceService | undefined;

export function getWorkspaceService(): WorkspaceService {
  if (singleton === undefined) {
    singleton = new WorkspaceService();
  }
  return singleton;
}
