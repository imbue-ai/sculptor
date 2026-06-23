import type { FastifyInstance } from "fastify";

import { getExpectedSessionToken, SESSION_TOKEN_HEADER_NAME } from "~/auth/session_token";

// GET /api/v1/session-token: plant the configured token as a SameSite=Strict,
// HttpOnly cookie so a direct-browser client (no Electron) can authenticate,
// then return 204 with no body. Mirrors set_session_token_cookie in web/app.py.
// This route is in the auth exempt list so it is reachable without a token.
export async function registerSessionTokenRoutes(app: FastifyInstance): Promise<void> {
  app.get("/api/v1/session-token", async (_request, reply) => {
    const token = getExpectedSessionToken() ?? "";
    await reply
      .header("set-cookie", `${SESSION_TOKEN_HEADER_NAME}=${token}; Path=/; SameSite=Strict; HttpOnly`)
      .code(204)
      .send();
  });
}
