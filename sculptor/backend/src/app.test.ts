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
