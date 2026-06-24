import { appendFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { runGit } from "~/git";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

async function commitAll(cwd: string, message: string): Promise<void> {
  await runGit(["add", "-A"], cwd);
  await runGit(
    ["-c", "user.email=t@t.co", "-c", "user.name=t", "commit", "-m", message],
    cwd,
  );
}

describe("workspace file routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;
  let workspaceId: string;
  let workingDir: string;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-wf-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    closeDatabase();
    ensureSculptorFolderReady(process.env);
    runMigrations(getDatabase(), MIGRATIONS_FOLDER);
    app = buildApp();
    await app.ready();

    projectDir = mkdtempSync(path.join(tmpdir(), "sculptor-repo-"));
    writeFileSync(path.join(projectDir, "README.md"), "# demo\n");
    await app.inject({
      method: "POST",
      url: "/api/v1/projects/init-git",
      payload: { projectPath: projectDir },
    });
    // init-git makes an empty commit; commit README.md so it is tracked and the
    // worktree checkout (and read-file) sees it.
    await commitAll(projectDir, "add readme");
    const project = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: projectDir },
    });
    const projectId = project.json().objectId;
    await app.inject({
      method: "PUT",
      url: `/api/v1/projects/${projectId}/workspace_setup_command`,
      payload: { workspaceSetupCommand: "" },
    });
    const branch = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${projectId}/current_branch`,
    });
    const sourceBranch = branch.json().currentBranch;
    const ws = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces",
      payload: {
        projectId,
        initializationStrategy: "WORKTREE",
        requestedBranchName: "feat",
        sourceBranch,
      },
    });
    workspaceId = ws.json().objectId;
    workingDir = path.join(ws.json().environmentId, "code");
  });

  afterEach(async () => {
    await app.close();
    closeDatabase();
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
    rmSync(projectDir, { recursive: true, force: true });
  });

  it("returns the uncommitted diff", async () => {
    appendFileSync(path.join(workingDir, "README.md"), "more\n");
    const res = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/diff`,
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().diff.objectType).toBe("DiffArtifact");
    expect(res.json().diff.uncommittedDiff).toContain("README.md");
  });

  it("lists commits and a single commit diff", async () => {
    writeFileSync(path.join(workingDir, "feature.txt"), "hello\n");
    await commitAll(workingDir, "add feature");
    const commits = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/commits`,
    });
    expect(commits.statusCode).toBe(200);
    const hashes = (
      commits.json().commits as { hash: string; message: string }[]
    ).map((c) => c.message);
    expect(hashes).toContain("add feature");

    const head = (commits.json().commits as { hash: string }[])[0]!.hash;
    const cdiff = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/commit-diff?commit_hash=${head}`,
    });
    expect(cdiff.statusCode).toBe(200);
    expect(cdiff.json().commitHash).toBe(head);
    expect(cdiff.json().diff).toContain("feature.txt");
  });

  it("reads a file as utf-8 and lists files", async () => {
    const read = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/read-file`,
      payload: { filePath: "README.md" },
    });
    expect(read.statusCode).toBe(200);
    expect(read.json().encoding).toBe("utf-8");
    expect(read.json().content).toContain("# demo");

    const missing = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/read-file`,
      payload: { filePath: "nope.txt" },
    });
    expect(missing.statusCode).toBe(404);

    const files = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/files`,
    });
    expect(
      (files.json().files as { path: string }[]).map((f) => f.path),
    ).toContain("README.md");
  });

  it("reads a file at a git ref", async () => {
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/read-file-at-ref`,
      payload: { path: "README.md", gitRef: "HEAD" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().content).toContain("# demo");
  });

  it("404s for an unknown workspace", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/workspaces/ws_missing/diff",
    });
    expect(res.statusCode).toBe(404);
  });
});
