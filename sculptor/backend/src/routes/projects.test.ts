import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
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

describe("project routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-proj-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    closeDatabase();
    ensureSculptorFolderReady(process.env);
    runMigrations(getDatabase(), MIGRATIONS_FOLDER);
    app = buildApp();
    await app.ready();
    // A real git repo to register (init-git creates .git + an initial commit).
    projectDir = mkdtempSync(path.join(tmpdir(), "sculptor-repo-"));
    writeFileSync(path.join(projectDir, "README.md"), "# demo\n");
    const init = await app.inject({
      method: "POST",
      url: "/api/v1/projects/init-git",
      payload: { projectPath: projectDir },
    });
    expect(init.statusCode).toBe(200);
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

  async function initialize(): Promise<string> {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: projectDir },
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.userGitRepoUrl).toBe(`file://${projectDir}`);
    expect(body.name).toBe(path.basename(projectDir));
    expect(body.organizationReference).toBe("local");
    return body.objectId as string;
  }

  it("initializes a project and lists it as active + MRU", async () => {
    const id = await initialize();
    const active = await app.inject({
      method: "GET",
      url: "/api/v1/projects/active",
    });
    expect(
      (active.json() as { objectId: string }[]).map((p) => p.objectId),
    ).toContain(id);

    const mru = await app.inject({
      method: "GET",
      url: "/api/v1/projects/most-recently-used",
    });
    expect(mru.json()).toBe(id);

    const all = await app.inject({ method: "GET", url: "/api/v1/projects" });
    expect(
      (all.json() as { objectId: string }[]).map((p) => p.objectId),
    ).toContain(id);
  });

  it("rejects re-adding the same repo", async () => {
    await initialize();
    const again = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: projectDir },
    });
    expect(again.statusCode).toBe(409);
  });

  it("returns 404 for a non-existent path and 400 for a non-git directory", async () => {
    const missing = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: path.join(dir, "nope") },
    });
    expect(missing.statusCode).toBe(404);

    const plainDir = mkdtempSync(path.join(tmpdir(), "sculptor-plain-"));
    const notGit = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: plainDir },
    });
    expect(notGit.statusCode).toBe(400);
    rmSync(plainDir, { recursive: true, force: true });
  });

  it("updates the setup command (tri-state) and naming pattern", async () => {
    const id = await initialize();
    const set = await app.inject({
      method: "PUT",
      url: `/api/v1/projects/${id}/workspace_setup_command`,
      payload: { workspaceSetupCommand: "npm ci" },
    });
    expect(set.json()).toBe("npm ci");

    // Blank input strips to "" — stored as "" (disable), distinct from null.
    const cleared = await app.inject({
      method: "PUT",
      url: `/api/v1/projects/${id}/workspace_setup_command`,
      payload: { workspaceSetupCommand: "  " },
    });
    expect(cleared.json()).toBe("");

    const pattern = await app.inject({
      method: "PUT",
      url: `/api/v1/projects/${id}/naming_pattern`,
      payload: { namingPattern: "<user>/<slug>" },
    });
    expect(pattern.json()).toBe("<user>/<slug>");
  });

  it("reports current branch, branch-exists, and repo info", async () => {
    const id = await initialize();
    const branch = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${id}/current_branch`,
    });
    expect(typeof branch.json().currentBranch).toBe("string");
    expect(branch.json().currentBranch.length).toBeGreaterThan(0);

    const current = branch.json().currentBranch as string;
    const exists = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${id}/branch-exists?name=${encodeURIComponent(current)}`,
    });
    expect(exists.json().exists).toBe(true);

    const missing = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${id}/branch-exists?name=no-such-branch`,
    });
    expect(missing.json().exists).toBe(false);

    const info = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${id}/repo_info`,
    });
    expect(info.json().projectId).toBe(id);
    expect(info.json().repoPath).toBe(projectDir);
    expect(info.json().isGithubOrigin).toBe(false);
  });

  it("lists files and folders, dirs first with trailing slash", async () => {
    const id = await initialize();
    mkdirSync(path.join(projectDir, "src"));
    writeFileSync(path.join(projectDir, "a.txt"), "x");
    const res = await app.inject({
      method: "GET",
      url: `/api/v1/projects/${id}/files_and_folders`,
    });
    const entries = res.json() as string[];
    expect(entries).toContain("src/");
    expect(entries).toContain("a.txt");
    expect(entries.indexOf("src/")).toBeLessThan(entries.indexOf("a.txt"));
  });

  it("soft-deletes a project", async () => {
    const id = await initialize();
    const del = await app.inject({
      method: "DELETE",
      url: `/api/v1/projects/${id}`,
    });
    expect(del.statusCode).toBe(200);
    const active = await app.inject({
      method: "GET",
      url: "/api/v1/projects/active",
    });
    expect(
      (active.json() as { objectId: string }[]).map((p) => p.objectId),
    ).not.toContain(id);
  });

  it("create-initial-commit commits staged files in an existing repo", async () => {
    writeFileSync(path.join(projectDir, "new.txt"), "y");
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/projects/create-initial-commit",
      payload: { projectPath: projectDir },
    });
    expect(res.statusCode).toBe(200);
  });
});
