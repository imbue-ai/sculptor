import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("workspace routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;
  let projectId: string;
  let sourceBranch: string;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-ws-"));
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
    const project = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: projectDir },
    });
    projectId = project.json().objectId;
    // Disable the project's setup command so create() doesn't spawn an async
    // setup subprocess that could outlive the test.
    await app.inject({
      method: "PUT",
      url: `/api/v1/projects/${projectId}/workspace_setup_command`,
      payload: { workspaceSetupCommand: "" },
    });
    const branch = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${projectId}/current_branch`,
    });
    sourceBranch = branch.json().currentBranch;
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

  async function createWorktree(branchName: string): Promise<string> {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces",
      payload: {
        projectId,
        initializationStrategy: "WORKTREE",
        requestedBranchName: branchName,
        sourceBranch,
      },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.initializationStrategy).toBe("WORKTREE");
    expect(body.requestedBranchName).toBe(branchName);
    expect(body.environmentId).not.toBeNull();
    expect(body.setup.status).toBe("not_configured");
    return body.objectId as string;
  }

  it("creates a worktree workspace and lists it", async () => {
    const id = await createWorktree("feature-a");
    const got = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${id}`,
    });
    expect(got.json().objectId).toBe(id);

    const list = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${projectId}/workspaces`,
    });
    expect(
      (list.json() as { objectId: string }[]).map((w) => w.objectId),
    ).toContain(id);

    const recent = await app.inject({
      method: "GET",
      url: "/api/v1/workspaces/recent",
    });
    expect(
      (recent.json().workspaces as { objectId: string }[]).map(
        (w) => w.objectId,
      ),
    ).toContain(id);
  });

  it("enforces per-strategy branch validation", async () => {
    const noBranch = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces",
      payload: { projectId, initializationStrategy: "WORKTREE", sourceBranch },
    });
    expect(noBranch.statusCode).toBe(400);

    const inPlaceWithBranch = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces",
      payload: {
        projectId,
        initializationStrategy: "IN_PLACE",
        requestedBranchName: "nope",
      },
    });
    expect(inPlaceWithBranch.statusCode).toBe(422);
  });

  it("previews a branch name", async () => {
    const res = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/preview-branch-name?project_id=${projectId}&workspace_name=My%20Feature&mode=WORKTREE`,
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().branchName.length).toBeGreaterThan(0);
  });

  it("batch-updates open state", async () => {
    const id = await createWorktree("feature-b");
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces/batch-update-open-state",
      payload: { workspaceIds: [id], isOpen: false },
    });
    expect(res.statusCode).toBe(200);
    const got = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${id}`,
    });
    expect(got.json().isOpen).toBe(false);
  });

  it("soft-deletes a workspace", async () => {
    const id = await createWorktree("feature-c");
    const del = await app.inject({
      method: "DELETE",
      url: `/api/v1/workspaces/${id}`,
    });
    expect(del.statusCode).toBe(200);
    const got = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${id}`,
    });
    expect(got.statusCode).toBe(404);
  });

  it("rerun reports no setup command configured when disabled", async () => {
    const id = await createWorktree("feature-d");
    const rerun = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${id}/setup/rerun`,
    });
    expect(rerun.statusCode).toBe(422);
  });
});
