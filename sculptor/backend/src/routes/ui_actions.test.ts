import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { eventBus } from "~/events";
import type { BusEvent } from "~/events/types";
import { runGit } from "~/git";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("workspace UI-action routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;
  let workspaceId: string;
  let workingDir: string;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-ui-"));
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

  function captureEvents(): { events: BusEvent[]; stop: () => void } {
    const events: BusEvent[] = [];
    const stop = eventBus.subscribe((event) => events.push(event));
    return { events, stop };
  }

  it("open-file publishes a ui_open_file action", async () => {
    const { events, stop } = captureEvents();
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/ui/open-file`,
      payload: { filePath: "README.md", mode: "auto" },
    });
    stop();
    expect(res.statusCode).toBe(204);
    const event = events.find((e) => e.kind === "ui_open_file");
    expect(event).toBeDefined();
    const action = (event as { action: Record<string, unknown> }).action;
    expect(action.mode).toBe("auto");
    expect(String(action.file_path)).toContain("README.md");
  });

  it("webview navigate + refresh publish ordered commands", async () => {
    const { events, stop } = captureEvents();
    await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/ui/webview/navigate`,
      payload: { url: "https://example.com" },
    });
    await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/ui/webview/refresh`,
    });
    stop();
    const commands = events
      .filter((e) => e.kind === "ui_webview_command")
      .map((e) => (e as { command: Record<string, unknown> }).command);
    expect(commands.map((c) => c.kind)).toEqual(["navigate", "refresh"]);
    expect(commands[0]!.seq).toBe(1);
    expect(commands[1]!.seq).toBe(2);
    expect(commands[0]!.url).toBe("https://example.com");
  });

  it("discard-file restores a modified tracked file", async () => {
    const readme = path.join(workingDir, "README.md");
    writeFileSync(readme, "# changed\n");
    const res = await app.inject({
      method: "POST",
      url: `/api/v1/workspaces/${workspaceId}/discard-file`,
      payload: { filePath: "README.md" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().result.success).toBe(true);
    expect(readFileSync(readme, "utf8")).toBe("# demo\n");
  });

  it("404s open-file for an unknown workspace", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/workspaces/ws_missing/ui/open-file",
      payload: { filePath: "README.md", mode: "auto" },
    });
    expect(res.statusCode).toBe(404);
  });
});
