import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";

const INDEX_HTML = "<!doctype html><html><head></head><body>sculptor spa</body></html>";
const APP_JS = "console.log('app');";

describe("static SPA serving", () => {
  let staticDir: string;
  let previousStaticDir: string | undefined;
  let previousSessionToken: string | undefined;

  beforeAll(() => {
    staticDir = mkdtempSync(path.join(tmpdir(), "sculptor-static-"));
    writeFileSync(path.join(staticDir, "index.html"), INDEX_HTML);
    mkdirSync(path.join(staticDir, "assets"));
    writeFileSync(path.join(staticDir, "assets", "app.js"), APP_JS);
  });

  afterAll(() => {
    rmSync(staticDir, { recursive: true, force: true });
  });

  beforeEach(() => {
    previousStaticDir = process.env.SCULPTOR_STATIC_DIR;
    previousSessionToken = process.env.SESSION_TOKEN;
    process.env.SCULPTOR_STATIC_DIR = staticDir;
  });

  afterEach(() => {
    if (previousStaticDir === undefined) {
      delete process.env.SCULPTOR_STATIC_DIR;
    } else {
      process.env.SCULPTOR_STATIC_DIR = previousStaticDir;
    }
    if (previousSessionToken === undefined) {
      delete process.env.SESSION_TOKEN;
    } else {
      process.env.SESSION_TOKEN = previousSessionToken;
    }
  });

  it("serves index.html and hashed assets from the asset dir", async () => {
    delete process.env.SESSION_TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const index = await app.inject({ method: "GET", url: "/" });
      expect(index.statusCode).toBe(200);
      expect(index.body).toContain("sculptor spa");

      const asset = await app.inject({ method: "GET", url: "/assets/app.js" });
      expect(asset.statusCode).toBe(200);
      expect(asset.body).toContain("console.log");
    } finally {
      await app.close();
    }
  });

  it("falls back to index.html for unknown non-API GET paths", async () => {
    delete process.env.SESSION_TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const spaRoute = await app.inject({ method: "GET", url: "/projects/some-id/agents" });
      expect(spaRoute.statusCode).toBe(200);
      expect(spaRoute.body).toContain("sculptor spa");
    } finally {
      await app.close();
    }
  });

  it("does not let the SPA fallback capture /api/* or /_* routes", async () => {
    delete process.env.SESSION_TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const unknownApi = await app.inject({ method: "GET", url: "/api/v1/does-not-exist" });
      expect(unknownApi.statusCode).toBe(404);
      expect(unknownApi.body).not.toContain("sculptor spa");

      const internal = await app.inject({ method: "GET", url: "/_internal/whatever" });
      expect(internal.statusCode).toBe(404);
    } finally {
      await app.close();
    }
  });

  it("keeps health and static reachable without a session token when auth is enabled", async () => {
    process.env.SESSION_TOKEN = "tok";
    const app = buildApp();
    await app.ready();
    try {
      const health = await app.inject({ method: "GET", url: "/api/v1/health" });
      expect(health.statusCode).toBe(200);

      const index = await app.inject({ method: "GET", url: "/" });
      expect(index.statusCode).toBe(200);
      expect(index.body).toContain("sculptor spa");
    } finally {
      await app.close();
    }
  });
});
