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
import { createOrm } from "~/db/orm";
import { getAgent, updateAgent } from "~/db/repositories";
import { runGit } from "~/git";
import { resetAgentRunnerForTests } from "~/runner/instance";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("agent lifecycle routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;
  let workspaceId: string;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-agent-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    closeDatabase();
    resetAgentRunnerForTests();
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
    await runGit(["add", "-A"], projectDir);
    await runGit(
      ["-c", "user.email=t@t.co", "-c", "user.name=t", "commit", "-m", "add"],
      projectDir,
    );
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
    const ws = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces",
      payload: {
        projectId,
        initializationStrategy: "WORKTREE",
        requestedBranchName: "feat",
        sourceBranch: branch.json().currentBranch,
      },
    });
    workspaceId = ws.json().objectId;
  });

  afterEach(async () => {
    await app.close();
    closeDatabase();
    resetAgentRunnerForTests();
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
    rmSync(projectDir, { recursive: true, force: true });
  });

  // A waiting (no-prompt) agent does not launch a harness, so tests stay
  // deterministic.
  async function createWaitingAgent(): Promise<string> {
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents`,
      payload: { agentType: "claude" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().objectType).toBe("CodingAgentTaskView");
    expect(res.json().taskId.startsWith("agt_")).toBe(true);
    return res.json().taskId as string;
  }

  it("creates a waiting agent and lists it", async () => {
    const id = await createWaitingAgent();
    const list = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/agents`,
    });
    expect(
      (list.json() as { taskId: string }[]).map((a) => a.taskId),
    ).toContain(id);
  });

  it("rejects a prompt without a model", async () => {
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents`,
      payload: { prompt: "do the thing" },
    });
    expect(res.statusCode).toBe(422);
  });

  it("resolves an agent by full id and short prefix, 404/409 otherwise", async () => {
    const id = await createWaitingAgent();
    const full = await app.inject({
      method: "GET",
      url: `/api/v1/agents/by-prefix/${id}`,
    });
    expect(full.json().agentId).toBe(id);

    const short = await app.inject({
      method: "GET",
      url: `/api/v1/agents/by-prefix/${id.slice(0, 10)}`,
    });
    expect(short.json().agentId).toBe(id);

    const missing = await app.inject({
      method: "GET",
      url: "/api/v1/agents/by-prefix/agt_zzzzzzzz",
    });
    expect(missing.statusCode).toBe(404);
  });

  it("soft-deletes an agent", async () => {
    const id = await createWaitingAgent();
    const del = await app.inject({
      method: "DELETE",
      url: `/api/v1/workspaces/${workspaceId}/agents/${id}`,
    });
    expect(del.statusCode).toBe(200);
    const list = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/agents`,
    });
    expect(
      (list.json() as { taskId: string }[]).map((a) => a.taskId),
    ).not.toContain(id);
  });

  it("restores a failed agent (re-queues it)", async () => {
    const id = await createWaitingAgent();
    // Force FAILED with a no-harness config so restore's re-supervision is a no-op.
    const orm = createOrm(getDatabase());
    updateAgent(orm, id, {
      runState: "FAILED",
      agentConfig: { object_type: "TerminalAgentConfig" },
    });
    const restore = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents/${id}/restore`,
    });
    expect(restore.statusCode).toBe(200);
    expect(getAgent(orm, id)?.runState).toBe("QUEUED");

    // Restoring a non-failed agent is a 400.
    const again = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents/${id}/restore`,
    });
    expect(again.statusCode).toBe(400);
  });

  it("returns diagnostics for an agent", async () => {
    const id = await createWaitingAgent();
    const res = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/agents/${id}/diagnostics`,
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toHaveProperty("sessionId");
    expect(res.json()).toHaveProperty("sculptorTranscriptFilePath");
  });

  it("404s an unknown artifact path and 400s an unknown name", async () => {
    const id = await createWaitingAgent();
    const unknown = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/agents/${id}/artifacts/BOGUS`,
    });
    expect(unknown.statusCode).toBe(400);
    const missing = await app.inject({
      method: "GET",
      url: `/api/v1/workspaces/${workspaceId}/agents/${id}/artifacts/DIFF`,
    });
    expect(missing.statusCode).toBe(404);
  });
});
