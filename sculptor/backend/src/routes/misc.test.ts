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
const BOUNDARY = "----sculptortest";

function multipart(
  filename: string,
  content: Buffer,
): { body: Buffer; headers: Record<string, string> } {
  const head = Buffer.from(
    `--${BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\n` +
      `Content-Type: application/octet-stream\r\n\r\n`,
  );
  const tail = Buffer.from(`\r\n--${BOUNDARY}--\r\n`);
  return {
    body: Buffer.concat([head, content, tail]),
    headers: { "content-type": `multipart/form-data; boundary=${BOUNDARY}` },
  };
}

describe("misc + uploads routes", () => {
  let dir: string;
  let projectDir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-misc-"));
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

  it("uploads a file and serves it back", async () => {
    const content = Buffer.from("hello upload world");
    const { body, headers } = multipart("note.txt", content);
    const up = await app.inject({
      method: "POST",
      url: "/api/v1/upload-file",
      payload: body,
      headers,
    });
    expect(up.statusCode).toBe(200);
    const fileId = up.json().fileId as string;
    expect(fileId.endsWith(".txt")).toBe(true);

    const served = await app.inject({
      method: "GET",
      url: `/api/v1/uploaded-file/${fileId}`,
    });
    expect(served.statusCode).toBe(200);
    expect(served.rawPayload.equals(content)).toBe(true);
  });

  it("rejects an oversize upload with 413", async () => {
    const big = Buffer.alloc(20 * 1024 * 1024 + 1024, 0x61);
    const { body, headers } = multipart("big.bin", big);
    const up = await app.inject({
      method: "POST",
      url: "/api/v1/upload-file",
      payload: body,
      headers,
    });
    expect(up.statusCode).toBe(413);
  });

  it("guards uploaded-file against traversal and missing ids", async () => {
    const traversal = await app.inject({
      method: "GET",
      url: "/api/v1/uploaded-file/..%2F..%2Fetc%2Fpasswd",
    });
    expect([400, 404]).toContain(traversal.statusCode);
    const missing = await app.inject({
      method: "GET",
      url: "/api/v1/uploaded-file/nope.txt",
    });
    expect(missing.statusCode).toBe(404);
  });

  it("lists skills from the project's .claude/skills", async () => {
    const project = await app.inject({
      method: "POST",
      url: "/api/v1/projects/initialize",
      payload: { projectPath: projectDir },
    });
    const projectId = project.json().objectId;
    const skillDir = path.join(projectDir, ".claude", "skills", "demo-skill");
    mkdirSync(skillDir, { recursive: true });
    writeFileSync(
      path.join(skillDir, "SKILL.md"),
      "---\nname: demo-skill\ndescription: A demo skill\n---\nbody\n",
    );
    const res = await app.inject({
      method: "GET",
      url: `/api/v1/skills?projectId=${projectId}`,
    });
    expect(res.statusCode).toBe(200);
    const names = (res.json() as { name: string }[]).map((s) => s.name);
    expect(names).toContain("demo-skill");
  });

  it("400s skills when neither id is provided", async () => {
    const res = await app.inject({ method: "GET", url: "/api/v1/skills" });
    expect(res.statusCode).toBe(400);
  });

  it("lists directories for autocomplete", async () => {
    mkdirSync(path.join(projectDir, "subdir"));
    const res = await app.inject({
      method: "GET",
      url: `/api/v1/filesystem/list?path=${encodeURIComponent(projectDir)}`,
    });
    expect(res.statusCode).toBe(200);
    expect((res.json() as { name: string }[]).map((e) => e.name)).toContain(
      "subdir",
    );
  });

  it("accepts a trace batch", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/trace/batch",
      payload: { spans: [] },
    });
    expect(res.statusCode).toBe(204);
  });

  it("reports failure for an unknown open-path app", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/open-path-in-app",
      payload: { path: projectDir, app: "nonsense" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().success).toBe(false);
  });
});
