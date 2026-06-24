import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";

describe("dependency routes", () => {
  let dir: string;
  let app: FastifyInstance;
  let previousFolder: string | undefined;

  beforeEach(async () => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-deproutes-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
    delete process.env.SESSION_TOKEN;
    // Raise the dependency probe timeout so concurrent-suite subprocess load
    // can't trip the 5s default.
    process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS = "30000";
    ensureSculptorFolderReady(process.env);
    app = buildApp();
    await app.ready();
  });

  afterEach(async () => {
    await app.close();
    delete process.env.SCULPTOR_DEP_PROBE_TIMEOUT_MS;
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  it("returns the three dependency infos", async () => {
    const res = await app.inject({
      method: "GET",
      url: "/api/v1/config/dependencies",
    });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(Object.keys(body).sort()).toEqual(["claude", "git", "pi"]);
    expect(typeof body.git.installed).toBe("boolean");
  });

  it("install of an unmanaged tool returns a failed InstallResult", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/dependencies/install?tool=GIT",
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().success).toBe(false);
    expect(res.json().error).toContain("not supported");
  });

  it("rejects an unknown tool with 400", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/dependencies/install?tool=BOGUS",
    });
    expect(res.statusCode).toBe(400);
    expect(res.json().detail).toContain("Unknown tool");
  });

  it("auth start for a non-Claude tool fails cleanly", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/dependencies/auth?tool=GIT",
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().success).toBe(false);
  });

  it("submitting a code with no session in progress fails cleanly", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/api/v1/dependencies/auth/code",
      payload: { code: "xyz" },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().success).toBe(false);
    expect(res.json().error).toContain("No sign-in");
  });
});
