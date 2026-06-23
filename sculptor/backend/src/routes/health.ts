import os from "node:os";

import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

// Mirrors HealthCheckResponse in sculptor/sculptor/web/data_types.py. The field
// names and types are part of the held-fixed API contract (RW-API-1); the
// service-derived values (disk, task count, dependencies) stay at their
// defaults until the relevant services land in later phases.
export const HealthCheckResponseSchema = z.object({
  version: z.string(),
  git_sha: z.string(),
  python_version: z.string(),
  platform: z.string(),
  platform_version: z.string(),
  free_disk_gb: z.number(),
  min_free_disk_gb: z.number(),
  free_disk_gb_warn_limit: z.number(),
  uptime_seconds: z.number(),
  active_task_count: z.number().int(),
  data_directory: z.string(),
  install_mode: z.string(),
  install_path: z.string(),
  ci_job_id: z.string().nullable().default(null),
  ci_ref: z.string().nullable().default(null),
  dependencies_status: z.unknown().nullable().default(null),
});

export type HealthCheckResponse = z.infer<typeof HealthCheckResponseSchema>;

const PLATFORM_NAMES: Record<string, string> = {
  darwin: "Darwin",
  linux: "Linux",
  win32: "Windows",
};

export async function registerHealthRoutes(app: FastifyInstance): Promise<void> {
  app.withTypeProvider<ZodTypeProvider>().get(
    "/api/v1/health",
    {
      schema: {
        response: { 200: HealthCheckResponseSchema },
      },
    },
    async (): Promise<HealthCheckResponse> => {
      return {
        version: "0.0.0",
        git_sha: "",
        python_version: process.version,
        platform: PLATFORM_NAMES[process.platform] ?? process.platform,
        platform_version: os.release(),
        free_disk_gb: 0,
        min_free_disk_gb: 0,
        free_disk_gb_warn_limit: 0,
        uptime_seconds: process.uptime(),
        active_task_count: 0,
        data_directory: "",
        install_mode: "source",
        install_path: "",
        ci_job_id: null,
        ci_ref: null,
        dependencies_status: null,
      };
    },
  );
}
