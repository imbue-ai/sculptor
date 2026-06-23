import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildApp } from "~/app";

const TOKEN = "test-token-abc123";

describe("session-token auth", () => {
  let previous: string | undefined;

  beforeEach(() => {
    previous = process.env.SESSION_TOKEN;
  });

  afterEach(() => {
    if (previous === undefined) {
      delete process.env.SESSION_TOKEN;
    } else {
      process.env.SESSION_TOKEN = previous;
    }
  });

  it("GET /api/v1/session-token returns 204 and plants the token cookie", async () => {
    process.env.SESSION_TOKEN = TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const response = await app.inject({ method: "GET", url: "/api/v1/session-token" });
      expect(response.statusCode).toBe(204);
      const setCookie = response.headers["set-cookie"];
      const cookieHeader = Array.isArray(setCookie) ? setCookie.join(";") : (setCookie ?? "");
      expect(cookieHeader).toContain(`x-session-token=${TOKEN}`);
      expect(cookieHeader).toContain("HttpOnly");
      expect(cookieHeader).toContain("SameSite=Strict");
    } finally {
      await app.close();
    }
  });

  it("403s a protected route with no token, including the error-code header", async () => {
    process.env.SESSION_TOKEN = TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const response = await app.inject({ method: "GET", url: "/api/v1/projects/most-recently-used" });
      expect(response.statusCode).toBe(403);
      expect(response.headers["x-error-code"]).toBe("invalid_session_token");
      expect(response.json()).toEqual({ detail: "Invalid or missing session token" });
    } finally {
      await app.close();
    }
  });

  it("accepts a protected route via header, query, or cookie token", async () => {
    process.env.SESSION_TOKEN = TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      // /health is exempt; use it as a protected-style probe is not valid, so we
      // assert the guard lets a valid token through to a non-existent route (404,
      // not 403) — proving auth passed.
      const viaHeader = await app.inject({
        method: "GET",
        url: "/api/v1/does-not-exist",
        headers: { "x-session-token": TOKEN },
      });
      expect(viaHeader.statusCode).toBe(404);

      const viaQuery = await app.inject({
        method: "GET",
        url: `/api/v1/does-not-exist?x-session-token=${TOKEN}`,
      });
      expect(viaQuery.statusCode).toBe(404);

      const viaCookie = await app.inject({
        method: "GET",
        url: "/api/v1/does-not-exist",
        headers: { cookie: `x-session-token=${TOKEN}` },
      });
      expect(viaCookie.statusCode).toBe(404);

      const wrong = await app.inject({
        method: "GET",
        url: "/api/v1/does-not-exist",
        headers: { "x-session-token": "wrong" },
      });
      expect(wrong.statusCode).toBe(403);
    } finally {
      await app.close();
    }
  });

  it("leaves health exempt and passes everything when SESSION_TOKEN is unset", async () => {
    delete process.env.SESSION_TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const health = await app.inject({ method: "GET", url: "/api/v1/health" });
      expect(health.statusCode).toBe(200);
      // Auth disabled: a protected route is reachable (404 for unknown, not 403).
      const unknown = await app.inject({ method: "GET", url: "/api/v1/does-not-exist" });
      expect(unknown.statusCode).toBe(404);
    } finally {
      await app.close();
    }
  });

  it("keeps /health reachable without a token when auth is enabled", async () => {
    process.env.SESSION_TOKEN = TOKEN;
    const app = buildApp();
    await app.ready();
    try {
      const health = await app.inject({ method: "GET", url: "/api/v1/health" });
      expect(health.statusCode).toBe(200);
    } finally {
      await app.close();
    }
  });
});
