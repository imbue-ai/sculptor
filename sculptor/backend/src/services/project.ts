import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

import { getInternalFolder } from "~/config/sculptor_folder";
import { getOrm } from "~/db/orm";
import {
  createRepo,
  getRepo,
  getWorkspace,
  listActiveRepos,
  listAgentsByWorkspace,
  listWorkspacesByRepo,
  softDeleteAgent,
  softDeleteRepo,
  softDeleteWorkspace,
  updateRepo,
} from "~/db/repositories";
import { CODE_SUBDIR, newWorkspaceRootPath } from "~/environment/paths";
import { eventBus } from "~/events";
import { runGit } from "~/git";
import { newRepoId } from "~/ids";
import { repo as repoTable, type RepoRow } from "~/db/schema";

// Project (internally `repo`) service: the TS port of
// sculptor/sculptor/services/project_service/ + the web/app.py project handlers.
// The wire keeps the `project`/`project_id` names even though the table is
// `repo` (RW-API-3); this layer owns that mapping.

// The rewrite is local-first single-org (REQ-SEC-002): the org column was
// dropped, but the wire Project still carries organizationReference (the
// frontend's typed client reads it). A stable constant satisfies it.
export const LOCAL_ORGANIZATION_REFERENCE = "local";

const MRU_FILE_NAME = "most_recently_used_project.txt";

export interface ProjectWire {
  createdAt: string;
  objectId: string;
  organizationReference: string;
  name: string;
  userGitRepoUrl: string | null;
  isPathAccessible: boolean;
  isDeleted: boolean;
  defaultSystemPrompt: string | null;
  workspaceSetupCommand: string | null;
  namingPattern: string | null;
}

export function repoRowToProjectWire(row: RepoRow): ProjectWire {
  return {
    createdAt: row.createdAt,
    objectId: row.objectId,
    organizationReference: LOCAL_ORGANIZATION_REFERENCE,
    name: row.name,
    userGitRepoUrl: row.userGitRepoUrl ?? null,
    isPathAccessible: row.isPathAccessible,
    isDeleted: row.isDeleted,
    defaultSystemPrompt: row.defaultSystemPrompt ?? null,
    workspaceSetupCommand: row.workspaceSetupCommand ?? null,
    namingPattern: row.namingPattern ?? null,
  };
}

// A file:// URL maps to a local path; mirrors Project.get_local_user_path.
export function localPathFromRepo(row: RepoRow): string | null {
  if (
    row.userGitRepoUrl === null ||
    !row.userGitRepoUrl.startsWith("file://")
  ) {
    return null;
  }
  return row.userGitRepoUrl.replace("file://", "");
}

// HTTP-shaped error the routes translate to a status + {detail}.
export class ProjectError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

// --- git helpers (foundation/git.py) ---------------------------------------

async function isPathInGitRepo(dir: string): Promise<boolean> {
  const result = await runGit(["rev-parse", "--is-inside-work-tree"], dir);
  return result.exitCode === 0 && result.stdout.trim() === "true";
}

async function resolveWorktreeToMainRepo(dir: string): Promise<string> {
  if (
    !existsSync(path.join(dir, ".git")) ||
    !statSync(path.join(dir, ".git")).isFile()
  ) {
    return dir;
  }
  const result = await runGit(
    ["rev-parse", "--path-format=absolute", "--git-common-dir"],
    dir,
  );
  if (result.exitCode !== 0) {
    return dir;
  }
  const mainRepo = path.dirname(result.stdout.trim());
  return existsSync(mainRepo) && statSync(mainRepo).isDirectory()
    ? mainRepo
    : dir;
}

async function hasAnyCommits(dir: string): Promise<boolean> {
  return (await runGit(["rev-parse", "--verify", "HEAD"], dir)).exitCode === 0;
}

function hostnameFromGitUrl(url: string): string {
  if (url.includes(":") && !/^(https?|ssh):\/\//.test(url)) {
    // SCP-style: git@github.com:org/repo.git
    return url.split("@", 2).pop()!.split(":")[0] ?? "";
  }
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

// --- the service ------------------------------------------------------------

export class ProjectService {
  // In-memory most-recent-first ordering of project ids (default_implementation
  // _active_projects). Seeded lazily from the MRU file + the DB.
  private activeOrder: string[] | undefined;

  private mruFilePath(): string {
    return path.join(getInternalFolder(), MRU_FILE_NAME);
  }

  getMostRecentlyUsed(): string | null {
    const file = this.mruFilePath();
    if (!existsSync(file)) {
      return null;
    }
    const id = readFileSync(file, "utf8").trim();
    return id.startsWith("prj_") ? id : null;
  }

  private writeMostRecentlyUsed(projectId: string): void {
    const file = this.mruFilePath();
    mkdirSync(path.dirname(file), { recursive: true });
    const tmp = `${file}.tmp`;
    writeFileSync(tmp, projectId);
    renameSync(tmp, file);
  }

  private order(): string[] {
    if (this.activeOrder === undefined) {
      const mru = this.getMostRecentlyUsed();
      this.activeOrder = mru === null ? [] : [mru];
    }
    return this.activeOrder;
  }

  activate(projectId: string): void {
    const order = this.order().filter((id) => id !== projectId);
    order.unshift(projectId);
    this.activeOrder = order;
    this.writeMostRecentlyUsed(projectId);
  }

  // get_active_projects: non-deleted projects, most-recently-activated first,
  // then the rest in creation order.
  getActiveProjects(): RepoRow[] {
    const repos = listActiveRepos(getOrm());
    const order = this.order();
    return [...repos].sort((a, b) => {
      const ia = order.indexOf(a.objectId);
      const ib = order.indexOf(b.objectId);
      const ra = ia === -1 ? Number.MAX_SAFE_INTEGER : ia;
      const rb = ib === -1 ? Number.MAX_SAFE_INTEGER : ib;
      return ra - rb;
    });
  }

  async initializeProject(rawPath: string): Promise<RepoRow> {
    const expanded = rawPath.startsWith("~")
      ? path.join(process.env.HOME ?? "", rawPath.slice(1))
      : rawPath;
    let projectPath = path.resolve(expanded);

    if (!existsSync(projectPath)) {
      throw new ProjectError(
        404,
        `Project path does not exist: ${projectPath}`,
      );
    }
    if (!statSync(projectPath).isDirectory()) {
      throw new ProjectError(
        400,
        `Project path is not a directory: ${projectPath}`,
      );
    }
    if (!existsSync(path.join(projectPath, ".git"))) {
      if (await isPathInGitRepo(projectPath)) {
        throw new ProjectError(
          400,
          "Selected directory is inside a git repository. Please select the root of the git repository.",
        );
      }
      throw new ProjectError(
        400,
        "Selected directory is not a git repository. Please initialize it first using /api/v1/projects/init-git",
      );
    }

    projectPath = await resolveWorktreeToMainRepo(projectPath);

    if (!(await hasAnyCommits(projectPath))) {
      throw new ProjectError(
        409,
        "Selected git repository has no commits. Please create an initial commit first.",
      );
    }

    const orm = getOrm();
    const url = `file://${projectPath}`;
    const name = path.basename(projectPath);
    // An ACTIVE repo at this path is a duplicate; a previously-DELETED one is
    // re-added by reusing (un-deleting) its row.
    const sameByPath = listAllRepos(orm).find(
      (repo) => localPathFromRepo(repo) === projectPath,
    );
    if (sameByPath !== undefined && !sameByPath.isDeleted) {
      throw new ProjectError(
        409,
        "This repository is already added to Sculptor.",
      );
    }

    const row =
      sameByPath === undefined
        ? createRepo(orm, { objectId: newRepoId(), name, userGitRepoUrl: url })
        : updateRepo(orm, sameByPath.objectId, {
            name,
            userGitRepoUrl: url,
            isDeleted: false,
          })!;
    this.activate(row.objectId);
    publishRepoChanged(row.objectId);
    return row;
  }

  deleteProject(projectId: string): void {
    const orm = getOrm();
    const repo = getRepo(orm, projectId);
    if (repo === undefined) {
      throw new ProjectError(404, "Project not found");
    }
    // Cascade: soft-delete agents then workspaces, then the project.
    for (const workspace of listWorkspacesByRepo(orm, projectId)) {
      for (const agent of listAgentsByWorkspace(orm, workspace.objectId)) {
        softDeleteAgent(orm, agent.objectId);
      }
      softDeleteWorkspace(orm, workspace.objectId);
    }
    softDeleteRepo(orm, projectId);
    this.activeOrder = this.order().filter((id) => id !== projectId);
    publishRepoChanged(projectId);
  }

  updateField(
    projectId: string,
    patch: {
      workspaceSetupCommand?: string | null;
      namingPattern?: string | null;
    },
  ): RepoRow {
    const orm = getOrm();
    const row = updateRepo(orm, projectId, patch);
    if (row === undefined) {
      throw new ProjectError(404, "Project not found");
    }
    this.activate(projectId);
    publishRepoChanged(projectId);
    return row;
  }
}

// listActiveRepos excludes soft-deleted rows; re-adding a previously-deleted
// repo reuses its row, so this scans every row by path.
function listAllRepos(orm: ReturnType<typeof getOrm>): RepoRow[] {
  return orm.select().from(repoTable).all();
}

function publishRepoChanged(projectId: string): void {
  eventBus.publish({
    kind: "data_model_change",
    changedEntities: [{ type: "repo", id: projectId }],
  });
}

// --- git init / initial commit ---------------------------------------------

export async function initGitRepo(rawPath: string): Promise<void> {
  const projectPath = path.resolve(
    rawPath.startsWith("~")
      ? path.join(process.env.HOME ?? "", rawPath.slice(1))
      : rawPath,
  );
  if (!existsSync(projectPath)) {
    throw new ProjectError(404, `Project path does not exist: ${projectPath}`);
  }
  if (!statSync(projectPath).isDirectory()) {
    throw new ProjectError(
      400,
      `Project path is not a directory: ${projectPath}`,
    );
  }
  if (existsSync(path.join(projectPath, ".git"))) {
    throw new ProjectError(
      400,
      `Directory is already a git repository: ${projectPath}`,
    );
  }
  const init = await runGit(["init"], projectPath);
  if (init.exitCode !== 0) {
    throw new ProjectError(
      500,
      `Failed to initialize git repository: ${init.stderr}`,
    );
  }
  const commit = await runGit(commitArgs("Initial commit"), projectPath);
  if (commit.exitCode !== 0) {
    throw new ProjectError(
      500,
      `Failed to initialize git repository: ${commit.stderr}`,
    );
  }
}

export async function createInitialCommit(rawPath: string): Promise<void> {
  const projectPath = path.resolve(
    rawPath.startsWith("~")
      ? path.join(process.env.HOME ?? "", rawPath.slice(1))
      : rawPath,
  );
  if (!existsSync(projectPath)) {
    throw new ProjectError(404, `Project path does not exist: ${projectPath}`);
  }
  if (!statSync(projectPath).isDirectory()) {
    throw new ProjectError(
      400,
      `Project path is not a directory: ${projectPath}`,
    );
  }
  const stage = await runGit(["add", "-A"], projectPath);
  if (stage.exitCode !== 0) {
    throw new ProjectError(
      500,
      `Failed to create initial commit: ${stage.stderr}`,
    );
  }
  const commit = await runGit(commitArgs("Initial commit"), projectPath);
  if (commit.exitCode !== 0) {
    throw new ProjectError(
      500,
      `Failed to create initial commit: ${commit.stderr}`,
    );
  }
}

// Commit with an inline identity so the command never fails on a machine
// without a configured git user.
function commitArgs(message: string): string[] {
  return [
    "-c",
    "user.email=sculptor@imbue.com",
    "-c",
    "user.name=Sculptor",
    "commit",
    "--allow-empty",
    "-m",
    message,
  ];
}

// --- read-only project queries ---------------------------------------------

function listDirectoryContents(
  root: string,
  directory: string,
  filter: string,
): string[] {
  const expanded = directory.startsWith("~")
    ? path.join(process.env.HOME ?? "", directory.slice(1))
    : directory;
  const target = path.isAbsolute(expanded)
    ? expanded
    : path.join(root, directory);
  let entries: { name: string; isDir: boolean }[];
  try {
    entries = readdirSync(target, { withFileTypes: true }).map((e) => ({
      name: e.name,
      isDir: e.isDirectory(),
    }));
  } catch {
    return [];
  }
  const lowerFilter = filter.toLowerCase();
  const filtered = entries.filter((e) =>
    e.name.toLowerCase().includes(lowerFilter),
  );
  const dirs = filtered
    .filter((e) => e.isDir)
    .map((e) => `${e.name}/`)
    .sort();
  const files = filtered
    .filter((e) => !e.isDir)
    .map((e) => e.name)
    .sort();
  return [...dirs, ...files];
}

export function filesAndFolders(
  projectId: string,
  directory: string,
  filter: string,
  workspaceId: string | null,
): string[] {
  const orm = getOrm();
  const repo = getRepo(orm, projectId);
  if (repo === undefined) {
    throw new ProjectError(404, "Project not found");
  }
  let root: string | null;
  if (workspaceId !== null) {
    const workspace = getWorkspace(orm, workspaceId);
    if (workspace === undefined) {
      throw new ProjectError(404, "Workspace not found");
    }
    root = path.join(newWorkspaceRootPath(workspace.objectId), CODE_SUBDIR);
  } else {
    root = localPathFromRepo(repo);
  }
  if (root === null) {
    return [];
  }
  return listDirectoryContents(root, directory, filter);
}

const REPO_ACCESS_MAX_RETRIES = 3;
const REPO_ACCESS_RETRY_DELAY_MS = 500;

async function withRetries<T>(operation: () => Promise<T>): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < REPO_ACCESS_MAX_RETRIES; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (error instanceof ProjectError) {
        throw error;
      }
      await new Promise((resolve) =>
        setTimeout(resolve, REPO_ACCESS_RETRY_DELAY_MS),
      );
    }
  }
  throw lastError;
}

function repoPathOr404(projectId: string): string {
  const repo = getRepo(getOrm(), projectId);
  if (repo === undefined) {
    throw new ProjectError(404, "Project not found");
  }
  if (!repo.isPathAccessible) {
    throw new ProjectError(404, "Project path is not accessible");
  }
  const local = localPathFromRepo(repo);
  if (local === null) {
    throw new ProjectError(500, "Git repository not found");
  }
  return local;
}

export async function getCurrentBranch(projectId: string): Promise<string> {
  const repoPath = repoPathOr404(projectId);
  return withRetries(async () => {
    const result = await runGit(
      ["rev-parse", "--abbrev-ref", "HEAD"],
      repoPath,
    );
    if (result.exitCode !== 0) {
      throw new ProjectError(404, "Failed to get current branch");
    }
    return result.stdout.trim();
  });
}

export async function checkBranchExists(
  projectId: string,
  name: string,
): Promise<boolean> {
  const trimmed = name.trim();
  if (trimmed === "") {
    return false;
  }
  const repo = getRepo(getOrm(), projectId);
  if (repo === undefined) {
    throw new ProjectError(404, "Project not found");
  }
  if (!repo.isPathAccessible) {
    return false;
  }
  const local = localPathFromRepo(repo);
  if (local === null) {
    return false;
  }
  const result = await runGit(
    ["rev-parse", "--verify", "--quiet", trimmed],
    local,
  );
  return result.exitCode === 0;
}

export interface RepoInfoWire {
  repoPath: string;
  currentBranch: string;
  recentBranches: string[];
  projectId: string;
  isGitlabOrigin: boolean;
  isGithubOrigin: boolean;
  remoteBranches: string[];
}

async function gitOutputOrNull(
  args: string[],
  cwd: string,
): Promise<string | null> {
  const result = await runGit(args, cwd);
  return result.exitCode === 0 ? result.stdout.trim() : null;
}

export async function getRepoInfo(projectId: string): Promise<RepoInfoWire> {
  const repoPath = repoPathOr404(projectId);
  return withRetries(async () => {
    const allBranches =
      (await gitOutputOrNull(
        ["branch", "--format=%(refname:short)"],
        repoPath,
      )) ?? "";
    const recentBranches = allBranches
      .split("\n")
      .map((b) => b.trim())
      .filter((b) => b !== "");
    const branch =
      (await gitOutputOrNull(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        repoPath,
      )) ?? "";
    const originUrl = await gitOutputOrNull(
      ["remote", "get-url", "origin"],
      repoPath,
    );
    const hostname =
      originUrl === null ? "" : hostnameFromGitUrl(originUrl).toLowerCase();
    const remoteRaw = await gitOutputOrNull(
      ["branch", "-r", "--format=%(refname:short)"],
      repoPath,
    );
    const remoteBranches =
      remoteRaw === null
        ? []
        : remoteRaw
            .split("\n")
            .map((b) => b.trim())
            .filter((b) => b.startsWith("origin/") && !b.includes("HEAD"));
    return {
      repoPath,
      currentBranch: branch,
      recentBranches,
      projectId,
      isGitlabOrigin: hostname.includes("gitlab"),
      isGithubOrigin: hostname.includes("github"),
      remoteBranches,
    };
  });
}

let singleton: ProjectService | undefined;

export function getProjectService(): ProjectService {
  if (singleton === undefined) {
    singleton = new ProjectService();
  }
  return singleton;
}
