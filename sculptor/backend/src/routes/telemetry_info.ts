import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import type { z } from "zod";

import {
  getCurrentUserConfig,
  getExecutionInstanceId,
  userConfigToWire,
} from "~/config/user_config";
import { TelemetryInfoSchema, UserConfigWireSchema } from "~/routes/config";

// GET /api/v1/telemetry_info (web/app.py): the telemetry info served to the
// frontend (which owns telemetry reporting). Pre-onboarding it falls back to the
// anonymous default config — getCurrentUserConfig already returns that when no
// config.toml exists, so this is one path.
export async function registerTelemetryInfoRoutes(
  app: FastifyInstance,
): Promise<void> {
  app
    .withTypeProvider<ZodTypeProvider>()
    .get(
      "/api/v1/telemetry_info",
      { schema: { response: { 200: TelemetryInfoSchema } } },
      async () => {
        const config = getCurrentUserConfig();
        return {
          userConfig: userConfigToWire(config) as z.infer<
            typeof UserConfigWireSchema
          >,
          sculptorVersion: "0.0.0",
          sculptorExecutionInstanceId: getExecutionInstanceId(),
        };
      },
    );
}
