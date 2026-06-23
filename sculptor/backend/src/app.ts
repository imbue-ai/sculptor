import fastifySwagger from "@fastify/swagger";
import Fastify, { type FastifyInstance } from "fastify";
import { jsonSchemaTransform, serializerCompiler, validatorCompiler } from "fastify-type-provider-zod";

import { registerAuthGuard } from "~/auth/guard";
import { registerHealthRoutes } from "~/routes/health";
import { registerSessionTokenRoutes } from "~/routes/session_token";

// Builds the Fastify application. This MUST stay free of side effects (no DB
// open, no service start) so unit tests can build it cheaply and --emit-openapi
// can produce the spec without a running backend. Route plugins register their
// Zod schemas here; any DB/service access happens at request time.
export function buildApp(): FastifyInstance {
  const app = Fastify({ logger: false });

  // Make Zod the single source of truth for route schemas, and feed those
  // schemas to @fastify/swagger so one OpenAPI document drives both client
  // generators (RW-API-4).
  app.setValidatorCompiler(validatorCompiler);
  app.setSerializerCompiler(serializerCompiler);

  void app.register(fastifySwagger, {
    openapi: {
      info: { title: "Sculptor", version: "0.0.0" },
    },
    transform: jsonSchemaTransform,
  });

  // The auth guard is a root-level onRequest hook, so it runs for every route
  // (including those registered by later plugins) regardless of order.
  registerAuthGuard(app);

  void app.register(registerSessionTokenRoutes);
  void app.register(registerHealthRoutes);

  return app;
}
