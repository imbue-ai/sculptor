import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

import {
  getExpectedSessionToken,
  hasValidToken,
  isProtectedPath,
  parseCookies,
  SESSION_TOKEN_HEADER_NAME,
} from "~/auth/session_token";

function firstHeaderValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

// Global onRequest guard enforcing the session token on protected HTTP routes.
// WebSocket upgrades are skipped here so the WS handler can accept-then-close
// with 4401 (browsers cannot set custom headers on WS); the WS endpoints reuse
// the same helpers. Mirrors SessionTokenMiddleware in web/auth.py: 403 with
// {"detail": ...} and an x-error-code header on failure.
export function registerAuthGuard(app: FastifyInstance): void {
  app.addHook("onRequest", async (request: FastifyRequest, reply: FastifyReply) => {
    const expectedToken = getExpectedSessionToken();
    if (expectedToken === undefined) {
      return;
    }
    if (request.method === "OPTIONS") {
      return;
    }
    if ((firstHeaderValue(request.headers.upgrade) ?? "").toLowerCase() === "websocket") {
      return;
    }

    const path = request.url.split("?", 1)[0] ?? request.url;
    if (!isProtectedPath(path)) {
      return;
    }

    const url = new URL(request.url, "http://localhost");
    const presented = {
      header: firstHeaderValue(request.headers[SESSION_TOKEN_HEADER_NAME]),
      query: url.searchParams.get(SESSION_TOKEN_HEADER_NAME) ?? undefined,
      cookie: parseCookies(request.headers.cookie)[SESSION_TOKEN_HEADER_NAME],
    };
    if (!hasValidToken(presented, expectedToken)) {
      await reply
        .code(403)
        .header("x-error-code", "invalid_session_token")
        .send({ detail: "Invalid or missing session token" });
    }
  });
}
