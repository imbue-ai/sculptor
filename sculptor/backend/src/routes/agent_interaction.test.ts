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
import {
  appendAgentMessage,
  getAgent,
  listAgentMessages,
  updateAgent,
} from "~/db/repositories";
import { runGit } from "~/git";
import { resetAgentRunnerForTests } from "~/runner/instance";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("agent interaction routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;
  let workspaceId: string;
  let agentId: string;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-ai-"));
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
    const agent = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents`,
      payload: { agentType: "claude" },
    });
    agentId = agent.json().taskId;
    // No-harness config so message-sending does not launch a real CLI.
    updateAgent(createOrm(getDatabase()), agentId, {
      agentConfig: { object_type: "TerminalAgentConfig" },
    });
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

  const url = (suffix: string): string =>
    `/api/v1/workspaces/${workspaceId}/agents/${agentId}${suffix}`;

  it("sends a message (appends it to the log)", async () => {
    const res = await app.inject({
      method: "POST",
      url: url("/messages"),
      payload: { message: "hello", model: "claude-opus-4-8" },
    });
    expect(res.statusCode).toBe(200);
    const messages = listAgentMessages(createOrm(getDatabase()), agentId);
    expect(
      messages.some((m) => (m.message as { text?: string }).text === "hello"),
    ).toBe(true);
  });

  it("answers a question", async () => {
    const res = await app.inject({
      method: "POST",
      url: url("/answer_question"),
      payload: {
        answers: { Q1: "yes" },
        questionData: { questions: [] },
        toolUseId: "toolu_1",
        model: "claude-opus-4-8",
      },
    });
    expect(res.statusCode).toBe(200);
    const messages = listAgentMessages(createOrm(getDatabase()), agentId);
    expect(
      messages.some(
        (m) =>
          (m.message as { object_type?: string }).object_type ===
          "UserQuestionAnswerMessage",
      ),
    ).toBe(true);
  });

  it("clears context (drops the session id)", async () => {
    updateAgent(createOrm(getDatabase()), agentId, {
      claudeSessionId: "sess_1",
    });
    const res = await app.inject({
      method: "POST",
      url: url("/clear_context"),
    });
    expect(res.statusCode).toBe(200);
    expect(
      getAgent(createOrm(getDatabase()), agentId)?.claudeSessionId,
    ).toBeNull();
  });

  it("interrupts (no-op when not running)", async () => {
    const res = await app.inject({ method: "POST", url: url("/interrupt") });
    expect(res.statusCode).toBe(200);
  });

  it("sets the model", async () => {
    const res = await app.inject({
      method: "POST",
      url: url("/set_model"),
      payload: { provider: "anthropic", modelId: "claude-opus-4-8" },
    });
    expect(res.statusCode).toBe(200);
    expect(getAgent(createOrm(getDatabase()), agentId)?.currentModel).toEqual({
      provider: "anthropic",
      model_id: "claude-opus-4-8",
    });
  });

  it("deletes a single message", async () => {
    const orm = createOrm(getDatabase());
    const row = appendAgentMessage(orm, agentId, {
      object_type: "ResponseBlockAgentMessage",
      message_id: "agm_del",
      source: "AGENT",
      text: "x",
    });
    const res = await app.inject({
      method: "DELETE",
      url: url(`/messages/${row.objectId}`),
    });
    expect(res.statusCode).toBe(200);
    expect(
      listAgentMessages(orm, agentId).some((m) => m.objectId === row.objectId),
    ).toBe(false);
  });

  it("404s interaction with an unknown agent", async () => {
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents/agt_missing/clear_context`,
    });
    expect(res.statusCode).toBe(404);
  });
});
