import fastifyCors from "@fastify/cors";
import fastifyMultipart from "@fastify/multipart";
import fastifySwagger from "@fastify/swagger";
import fastifyWebsocket from "@fastify/websocket";
import Fastify, { type FastifyBaseLogger, type FastifyInstance } from "fastify";
import {
  jsonSchemaTransform,
  serializerCompiler,
  validatorCompiler,
} from "fastify-type-provider-zod";

import { eventBus } from "~/events";
import { registerAgentInteractionRoutes } from "~/routes/agent_interaction";
import { registerAgentRoutes } from "~/routes/agents";
import { registerAuthGuard } from "~/auth/guard";
import { registerCiBabysitterRoutes } from "~/routes/ci_babysitter";
import { registerConfigRoutes } from "~/routes/config";
import { registerDependencyRoutes } from "~/routes/dependencies";
import { registerFilesystemRoutes } from "~/routes/filesystem";
import { registerHealthRoutes } from "~/routes/health";
import { registerProjectRoutes } from "~/routes/projects";
import { registerSkillRoutes } from "~/routes/skills";
import { registerTraceRoutes } from "~/routes/trace";
import { registerUploadRoutes } from "~/routes/uploads";
import { registerUiActionRoutes } from "~/routes/ui_actions";
import { registerWorkspaceFileRoutes } from "~/routes/workspace_files";
import { registerWorkspaceOsRoutes } from "~/routes/workspace_os";
import { registerWorkspaceRoutes } from "~/routes/workspaces";
import { registerSessionTokenRoutes } from "~/routes/session_token";
import { registerStreamWsRoutes } from "~/routes/stream_ws";
import { registerTelemetryInfoRoutes } from "~/routes/telemetry_info";
import { registerTerminalHttpRoutes } from "~/routes/terminal_http";
import { registerTerminalWsRoutes } from "~/routes/terminal_ws";
import { registerStatic } from "~/static";

export interface BuildAppOptions {
  // When provided, Fastify routes request/error logs through this logger so
  // they share the configured sink (Task 1.7). Omitted in unit tests / OpenAPI
  // emit so the app stays quiet and side-effect-free.
  loggerInstance?: FastifyBaseLogger;
}

// Builds the Fastify application. This MUST stay free of side effects (no DB
// open, no service start) so unit tests can build it cheaply and --emit-openapi
// can produce the spec without a running backend. Route plugins register their
// Zod schemas here; any DB/service access happens at request time.
export function buildApp(options: BuildAppOptions = {}): FastifyInstance {
  const app =
    options.loggerInstance !== undefined
      ? Fastify({ loggerInstance: options.loggerInstance })
      : Fastify({ logger: false });

  // Acknowledge every request that carries a client request id. The frontend's
  // request tracker holds each non-`skipWsAck` request open until the /stream/ws
  // connection echoes its id back in `finished_request_ids`, then resolves the
  // caller (web/auth.py opens+commits a per-request transaction in Python, which
  // emits the same ack on commit — including for reads like preview-branch-name).
  // A mutation publishes its data_model_change during the handler, so this
  // post-handler ack lands after the changed rows; reads carry no change and are
  // acked alone. Without this, a tracked read hangs until the 10 s client
  // timeout. The id header is set by every openapi-client request
  // (apiClient.ts `Sculptor-Request-ID`); the browser's WS/static fetches omit
  // it and are skipped.
  app.addHook("onResponse", async (request) => {
    const requestId = request.headers["sculptor-request-id"];
    if (typeof requestId === "string" && requestId !== "") {
      eventBus.publish({
        kind: "data_model_change",
        requestId,
        changedEntities: [],
      });
    }
  });

  // Make Zod the single source of truth for route schemas, and feed those
  // schemas to @fastify/swagger so one OpenAPI document drives both client
  // generators (RW-API-4).
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);

  // CORS — parity with the Python backend's CORSMiddleware (web/app.py). In dev
  // the renderer loads from a separate frontend origin (the backend runs
  // --no-serve-static and the SPA is served by the Vite/Electron dev server),
  // so every API call is cross-origin and the browser sends an OPTIONS
  // preflight; without this the preflight 404s and the renderer sees "Failed to
  // fetch". (Integration tests in the default `browser` launch mode load the SPA
  // from the backend's own origin, so they never exercised this.) Allow the
  // local frontend/backend origins, file:// renderers ("null"), and the packaged
  // custom protocol. `credentials: true` + an origin callback reflect the
  // specific origin (never a bare `*`), and leaving `allowedHeaders` unset
  // reflects the requested headers — matching FastAPI's allow_headers=["*"] +
  // allow_credentials=True behavior.
  void app.register(fastifyCors, {
    origin: (origin, cb) => {
      // Same-origin and non-browser requests carry no Origin header.
      if (origin === undefined) {
        cb(null, true);
        return;
      }
      const allowed =
        origin === "null" || // file:// renderer reports origin "null"
        origin === "sculptor://app" || // packaged renderer custom protocol
        /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin); // dev frontend / api on any localhost port
      cb(null, allowed);
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
  });

  void app.register(fastifySwagger, {
    openapi: {
      info: { title: "Sculptor", version: "0.0.0" },
    },
    transform: jsonSchemaTransform,
  });

  // @fastify/websocket must be registered before any route that uses
  // { websocket: true } (the /stream/ws channel).
  void app.register(fastifyWebsocket);

  // Multipart powers POST /api/v1/upload-file (the per-file size cap is applied
  // per-request in the handler, RW-NFR-051).
  void app.register(fastifyMultipart);

  // The auth guard is a root-level onRequest hook, so it runs for every route
  // (including those registered by later plugins) regardless of order.
  registerAuthGuard(app);

  void app.register(registerSessionTokenRoutes);
  void app.register(registerHealthRoutes);
  void app.register(registerConfigRoutes);
  void app.register(registerDependencyRoutes);
  void app.register(registerProjectRoutes);
  void app.register(registerWorkspaceRoutes);
  void app.register(registerWorkspaceFileRoutes);
  void app.register(registerUiActionRoutes);
  void app.register(registerWorkspaceOsRoutes);
  void app.register(registerAgentRoutes);
  void app.register(registerAgentInteractionRoutes);
  void app.register(registerCiBabysitterRoutes);
  void app.register(registerSkillRoutes);
  void app.register(registerFilesystemRoutes);
  void app.register(registerUploadRoutes);
  void app.register(registerTraceRoutes);
  void app.register(registerTerminalHttpRoutes);
  void app.register(registerTerminalWsRoutes);
  void app.register(registerTelemetryInfoRoutes);
  void app.register(registerStreamWsRoutes);

  // Static SPA serving + fallback, registered last so API routes win. A no-op
  // when no built frontend is present.
  registerStatic(app);

  return app;
}
