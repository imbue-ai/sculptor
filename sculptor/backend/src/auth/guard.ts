import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

import {
  getExpectedSessionToken,
  hasValidToken,
  isProtectedPath,
  parseCookies,
  redactSessionTokenInUrl,
  SESSION_TOKEN_HEADER_NAME,
} from "~/auth/session_token";

function firstHeaderValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

// Request log serializer mirroring Fastify's built-in `req` serializer, but with
// the session token stripped from the logged URL. Fastify's auto request logging
// records `req.url` verbatim, and that URL can carry the token as a query param
// (browsers cannot set custom headers on a WebSocket handshake), so without this
// the raw token would land in the app logs. Installed on the logger instance so
// it overrides the default serializer for every request log line.
export function redactingRequestLogSerializer(request: FastifyRequest): {
  method: string;
  url: string;
  version: string | undefined;
  host: string | undefined;
  remoteAddress: string | undefined;
  remotePort: number | undefined;
} {
  return {
    method: request.method,
    url: redactSessionTokenInUrl(request.url),
    version: firstHeaderValue(request.headers["accept-version"]),
    host: request.host,
    remoteAddress: request.ip,
    remotePort: request.socket?.remotePort,
  };
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
