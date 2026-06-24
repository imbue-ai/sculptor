import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { WebSocket } from "ws";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm } from "~/db/orm";
import { getAgent } from "~/db/repositories";
import { resetAgentRunnerForTests } from "~/runner/instance";
import { resetTerminalManagerForTests } from "~/terminal/instance";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("terminal routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let port: number;
  let previousFolder: string | undefined;
  let workspaceId: string;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-term-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    closeDatabase();
    resetAgentRunnerForTests();
    resetTerminalManagerForTests();
    ensureSculptorFolderReady(process.env);
    runMigrations(getDatabase(), MIGRATIONS_FOLDER);
    app = buildApp();
    await app.ready();
    await app.listen({ port: 0, host: "127.0.0.1" });
    port = (app.server.address() as AddressInfo).port;

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
    resetTerminalManagerForTests();
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

  it("streams PTY output over the workspace terminal WS and accepts input + resize", async () => {
    const socket = new WebSocket(
      `ws://127.0.0.1:${port}/api/v1/workspaces/${workspaceId}/terminal/0/ws`,
    );
    socket.binaryType = "arraybuffer";
    let output = "";
    const sawMarker = new Promise<void>((resolve, reject) => {
      socket.on("error", reject);
      socket.on("message", (data: ArrayBuffer) => {
        output += Buffer.from(data).toString("utf8");
        if (output.includes("term_marker_123")) {
          resolve();
        }
      });
      socket.on("open", () => {
        socket.send(JSON.stringify({ type: "resize", cols: 100, rows: 40 }));
        socket.send(new TextEncoder().encode("echo term_marker_123\n"));
      });
    });
    await sawMarker;
    socket.close();
    expect(output).toContain("term_marker_123");
  });

  it("closes a workspace terminal index", async () => {
    const res = await app.inject({
      method: "DELETE",
      url: `/api/v1/workspaces/${workspaceId}/terminal/0`,
    });
    expect(res.statusCode).toBe(200);
  });

  it("lists terminal-agent registrations (empty until Task 7.5)", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/terminal-agent-registrations",
    });
    expect(res.json()).toEqual({ registrations: [] });
  });

  it("persists a session id via the signal endpoint", async () => {
    const agent = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/agents`,
      payload: { agentType: "claude" },
    });
    const agentId = agent.json().taskId;
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/agents/${agentId}/signal`,
      payload: { event: "session-id", sessionId: "sess-abc_123" },
    });
    expect(res.statusCode).toBe(204);
    expect(getAgent(createOrm(getDatabase()), agentId)?.terminalSessionId).toBe(
      "sess-abc_123",
    );
  });

  it("404s terminal input for an unknown agent", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/agents/agt_missing/terminal/input",
      payload: { text: "hi", submit: true },
    });
    expect(res.statusCode).toBe(404);
  });
});
