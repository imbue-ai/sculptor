import { describe, expect, it } from "vitest";

import { buildApp } from "~/app";
import { generateOpenApiDocument } from "~/openapi";

describe("buildApp", () => {
  it("answers GET /api/v1/health with 200 and the health payload shape", async () => {
    const app = buildApp();
    await app.ready();
    try {
      const response = await app.inject({ method: "GET", url: "/api/v1/health" });
      expect(response.statusCode).toBe(200);
      const body = response.json();
      for (const field of [
        "version",
        "git_sha",
        "python_version",
        "platform",
        "platform_version",
        "free_disk_gb",
        "min_free_disk_gb",
        "free_disk_gb_warn_limit",
        "uptime_seconds",
        "active_task_count",
        "data_directory",
        "install_mode",
        "install_path",
      ]) {
        expect(body).toHaveProperty(field);
      }
    } finally {
      await app.close();
    }
  });
});

describe("CORS (cross-origin dev frontend → backend)", () => {
  // Regression: in dev the renderer loads from a separate frontend origin
  // (backend runs --no-serve-static), so every call is cross-origin and the
  // browser sends an OPTIONS preflight. Without @fastify/cors the backend 404s
  // the preflight and the renderer reports "Failed to fetch". The default
  // `browser`-mode integration suite loads the SPA from the backend's own
  // origin (same-origin), so it never caught this — hence this unit test.
  it("answers a cross-origin preflight from a localhost frontend origin", async () => {
    const app = buildApp();
    await app.ready();
    try {
      const origin = "http://localhost:48511";
      const response = await app.inject({
        method: "OPTIONS",
        url: "/api/v1/health",
        headers: {
          origin,
          "access-control-request-method": "POST",
          "access-control-request-headers": "x-session-token,content-type",
        },
      });
      expect(response.statusCode).toBeLessThan(300); // a real preflight response, not 404
      expect(response.headers["access-control-allow-origin"]).toBe(origin);
      expect(response.headers["access-control-allow-credentials"]).toBe("true");
    } finally {
      await app.close();
    }
  });

  it("reflects an allowed Origin and omits it for a disallowed one", async () => {
    const app = buildApp();
    await app.ready();
    try {
      const allowed = await app.inject({
        method: "GET",
        url: "/api/v1/health",
        headers: { origin: "http://127.0.0.1:5173" },
      });
      expect(allowed.headers["access-control-allow-origin"]).toBe("http://127.0.0.1:5173");

      const denied = await app.inject({
        method: "GET",
        url: "/api/v1/health",
        headers: { origin: "https://evil.example.com" },
      });
      expect(denied.headers["access-control-allow-origin"]).toBeUndefined();
    } finally {
      await app.close();
    }
  });
});

describe("generateOpenApiDocument", () => {
  it("emits an OpenAPI 3.x document that includes /api/v1/health", async () => {
    const document = (await generateOpenApiDocument()) as {
      openapi?: string;
      paths?: Record<string, unknown>;
    };
    expect(document.openapi).toMatch(/^3\./);
    expect(document.paths).toHaveProperty("/api/v1/health");
  });
});
