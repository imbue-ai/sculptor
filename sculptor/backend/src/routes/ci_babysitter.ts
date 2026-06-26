import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getCIBabysitterCoordinator } from "~/services/ci_babysitter/coordinator";

// CI babysitter status + pause endpoints (web/app.py). Off-by-default with a
// retry cap is enforced by the coordinator; these routes expose
// its per-workspace view and the pause toggle.

const StateViewSchema = z.object({
  workspaceId: z.string(),
  paused: z.boolean(),
  retryCount: z.number().int(),
  retryCap: z.number().int(),
  retired: z.boolean(),
  atCap: z.boolean(),
  disabledReason: z.string().nullable(),
  disabledReasonIsTransient: z.boolean(),
});

export async function registerCiBabysitterRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  typed.get(
    "/api/v1/workspaces/:workspace_id/ci_babysitter",
    {
      schema: {
        params: z.object({ workspace_id: z.string() }),
        response: { 200: StateViewSchema },
      },
    },
    async (request) =>
      getCIBabysitterCoordinator().buildView(request.params.workspace_id),
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/ci_babysitter/pause",
    {
      schema: {
        params: z.object({ workspace_id: z.string() }),
        body: z.object({ paused: z.boolean() }),
        response: { 200: StateViewSchema },
      },
    },
    async (request) => {
      const coordinator = getCIBabysitterCoordinator();
      coordinator.setPaused(
        request.params.workspace_id,
        "",
        request.body.paused,
      );
      return coordinator.buildView(request.params.workspace_id);
    },
  );
}
