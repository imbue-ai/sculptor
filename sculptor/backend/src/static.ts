import fastifyStatic from "@fastify/static";
import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

import { resolveStaticAssetDir } from "~/config/paths";

// Serves the built frontend SPA with single-page-app fallback, mirroring the
// Python catch-all in web/app.py: known files are served from frontend-dist,
// and unknown non-API GET paths return index.html so the client-side router can
// render the route. Unlike the Python catch-all, the fallback deliberately does
// NOT capture /api/* or the internal /_* routes (RW-SIMP) — those 404.
//
// Static assets and the SPA fallback are non-/api paths, so the session-token
// guard (which only protects /api/) lets them through without a token.
//
// Registration is a no-op when no built frontend is present (unit tests,
// OpenAPI emit), keeping buildApp cheap and side-effect-free in those cases.
export function registerStatic(app: FastifyInstance): void {
  const root = resolveStaticAssetDir();
  if (root === undefined) {
    return;
  }

  void app.register(fastifyStatic, { root, prefix: "/", wildcard: false });

  app.setNotFoundHandler((request: FastifyRequest, reply: FastifyReply) => {
    const pathname = request.url.split("?", 1)[0] ?? request.url;
    if (request.method === "GET" && !pathname.startsWith("/api") && !pathname.startsWith("/_")) {
      return reply.sendFile("index.html");
    }
    return reply.code(404).send({ detail: "Not Found" });
  });
}
