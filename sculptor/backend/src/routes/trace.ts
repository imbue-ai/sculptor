import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

// POST /api/v1/trace/batch (web/app.py). Accepts the frontend's trace batch.
// Forwarding to PostHog is consent-gated in the telemetry service (Task 7.7);
// until then we accept and drop so the client's batching path is satisfied.

export async function registerTraceRoutes(app: FastifyInstance): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  typed.post(
    "/api/v1/trace/batch",
    {
      schema: {
        body: z.object({}).passthrough(),
        response: { 204: z.null() },
      },
    },
    async (_request, reply) => reply.code(204).send(null),
  );
}
