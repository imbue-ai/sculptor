import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getDependencyService, type Dependency } from "~/services/dependencies";

// Dependency-management endpoints (web/app.py): status, managed install, and the
// two-step Claude device-code auth. Wire shapes are camelCase (RW-API-3); the
// service already produces them.

const VersionRangeInfoSchema = z.object({
  minVersion: z.string(),
  maxVersion: z.string(),
  recommendedVersion: z.string(),
});

const InstallProgressSchema = z.object({
  tool: z.string(),
  bytesDownloaded: z.number().int(),
  totalBytes: z.number().int().nullable(),
});

const DependencyInfoSchema = z.object({
  installed: z.boolean(),
  path: z.string().nullable(),
  version: z.string().nullable(),
  isOverride: z.boolean(),
  mode: z.enum(["MANAGED", "CUSTOM"]).nullable(),
  versionRange: VersionRangeInfoSchema.nullable(),
  isVersionInRange: z.boolean().nullable(),
  managedVersion: z.string().nullable(),
  isAuthenticated: z.boolean().nullable(),
  installProgress: InstallProgressSchema.nullable(),
  installError: z.string().nullable(),
});

const DependenciesStatusSchema = z.object({
  git: DependencyInfoSchema,
  claude: DependencyInfoSchema,
  pi: DependencyInfoSchema,
});

const InstallResultSchema = z.object({
  success: z.boolean(),
  inProgress: z.boolean(),
  version: z.string().nullable(),
  path: z.string().nullable(),
  error: z.string().nullable(),
});

const AuthStartResultSchema = z.object({
  authUrl: z.string().nullable(),
  needsCode: z.boolean(),
  success: z.boolean(),
  error: z.string().nullable(),
});

const AuthResultSchema = z.object({
  success: z.boolean(),
  authUrl: z.string().nullable(),
  error: z.string().nullable(),
});

const ErrorResponseSchema = z.object({ detail: z.string() });

const ToolQuerySchema = z.object({ tool: z.string().default("CLAUDE") });
const SubmitAuthCodeRequestSchema = z.object({
  code: z.string(),
  tool: z.string().default("CLAUDE"),
});

const VALID_TOOLS: ReadonlySet<string> = new Set(["CLAUDE", "GIT", "PI"]);

function parseTool(value: string): Dependency | null {
  return VALID_TOOLS.has(value) ? (value as Dependency) : null;
}

export async function registerDependencyRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  const service = getDependencyService();

  typed.get(
    "/api/v1/config/dependencies",
    { schema: { response: { 200: DependenciesStatusSchema } } },
    async () => service.getStatus(),
  );

  typed.post(
    "/api/v1/dependencies/install",
    {
      schema: {
        querystring: ToolQuerySchema,
        response: { 200: InstallResultSchema, 400: ErrorResponseSchema },
      },
    },
    async (request, reply) => {
      const tool = parseTool(request.query.tool);
      if (tool === null) {
        return reply
          .code(400)
          .send({ detail: `Unknown tool: ${request.query.tool}` });
      }
      return service.installManaged(tool);
    },
  );

  typed.post(
    "/api/v1/dependencies/auth",
    {
      schema: {
        querystring: ToolQuerySchema,
        response: { 200: AuthStartResultSchema, 400: ErrorResponseSchema },
      },
    },
    async (request, reply) => {
      const tool = parseTool(request.query.tool);
      if (tool === null) {
        return reply
          .code(400)
          .send({ detail: `Unknown tool: ${request.query.tool}` });
      }
      return service.startAuthLogin(tool);
    },
  );

  typed.post(
    "/api/v1/dependencies/auth/code",
    {
      schema: {
        body: SubmitAuthCodeRequestSchema,
        response: { 200: AuthResultSchema, 400: ErrorResponseSchema },
      },
    },
    async (request, reply) => {
      const tool = parseTool(request.body.tool);
      if (tool === null) {
        return reply
          .code(400)
          .send({ detail: `Unknown tool: ${request.body.tool}` });
      }
      return service.submitAuthCode(tool, request.body.code);
    },
  );
}
