import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { TelemetryEvent } from "~/telemetry/events";
import { capture } from "~/telemetry/posthog";

// POST /api/v1/trace/batch (web/app.py). Accepts the frontend's trace batch and
// forwards it through the consent gate + masking (Task 7.7). capture() no-ops
// unless analytics consent is granted and a backend token is configured, so a
// fresh / consent-declined instance emits nothing.

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
    async (request, reply) => {
      capture(
        TelemetryEvent.FrontendTraceBatch,
        request.body as Record<string, unknown>,
      );
      return reply.code(204).send(null);
    },
  );
}
