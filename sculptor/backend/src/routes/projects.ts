import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import {
  checkBranchExists,
  createInitialCommit,
  filesAndFolders,
  getCurrentBranch,
  getProjectService,
  getRepoInfo,
  initGitRepo,
  ProjectError,
  repoRowToProjectWire,
} from "~/services/project";

// Project (internally `repo`) endpoints (web/app.py). The wire keeps
// `projects`/`project_id`; the service owns the repo->project mapping.
// NOTE: POST /api/v1/projects/{id}/tasks (legacy create-agent) lands in Task 6.7
// alongside the agent-creation path it reuses.

const ProjectWireSchema = z.object({
  createdAt: z.string(),
  objectId: z.string(),
  organizationReference: z.string(),
  name: z.string(),
  userGitRepoUrl: z.string().nullable(),
  isPathAccessible: z.boolean(),
  isDeleted: z.boolean(),
  defaultSystemPrompt: z.string().nullable(),
  workspaceSetupCommand: z.string().nullable(),
  namingPattern: z.string().nullable(),
});

const RepoInfoSchema = z.object({
  repoPath: z.string(),
  currentBranch: z.string(),
  recentBranches: z.array(z.string()),
  projectId: z.string(),
  isGitlabOrigin: z.boolean(),
  isGithubOrigin: z.boolean(),
  remoteBranches: z.array(z.string()),
});

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = {
  400: ErrorResponseSchema,
  404: ErrorResponseSchema,
  409: ErrorResponseSchema,
  500: ErrorResponseSchema,
};

const ProjectPathRequestSchema = z.object({ projectPath: z.string() });
const ProjectIdParamsSchema = z.object({ project_id: z.string() });

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof ProjectError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  throw error;
}

// Fastify sends a bare string/null payload as text/plain (it bypasses
// serialization for string payloads). These endpoints return a JSON-encoded
// scalar (FastAPI's `-> str | None`), so encode + set the content type by hand.
function sendJsonScalar(
  reply: FastifyReply,
  value: string | null,
): FastifyReply {
  return reply
    .header("content-type", "application/json")
    .send(JSON.stringify(value));
}

export async function registerProjectRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  const service = getProjectService();

  typed.post(
    "/api/v1/projects/initialize",
    {
      schema: {
        body: ProjectPathRequestSchema,
        response: { 200: ProjectWireSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return repoRowToProjectWire(
          await service.initializeProject(request.body.projectPath),
        );
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/projects/active",
    { schema: { response: { 200: z.array(ProjectWireSchema) } } },
    async () => service.getActiveProjects().map(repoRowToProjectWire),
  );

  typed.get(
    "/api/v1/projects/most-recently-used",
    { schema: { response: { 200: z.string().nullable() } } },
    async (_request, reply) =>
      sendJsonScalar(reply, service.getMostRecentlyUsed()),
  );

  typed.get(
    "/api/v1/projects",
    { schema: { response: { 200: z.array(ProjectWireSchema) } } },
    async () => {
      // The unscoped list mirrors get_projects: all non-deleted projects.
      return service.getActiveProjects().map(repoRowToProjectWire);
    },
  );

  typed.delete(
    "/api/v1/projects/:project_id",
    {
      schema: {
        params: ProjectIdParamsSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.deleteProject(request.params.project_id);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/projects/init-git",
    {
      schema: {
        body: ProjectPathRequestSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        await initGitRepo(request.body.projectPath);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/projects/create-initial-commit",
    {
      schema: {
        body: ProjectPathRequestSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        await createInitialCommit(request.body.projectPath);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.put(
    "/api/v1/projects/:project_id/workspace_setup_command",
    {
      schema: {
        params: ProjectIdParamsSchema,
        body: z.object({ workspaceSetupCommand: z.string().nullable() }),
        response: { 200: z.string().nullable(), ...errorResponses },
      },
    },
    async (request, reply) => {
      // Tri-state: null resets to default; "" / blank disables (also null);
      // a value is the custom command.
      const raw = request.body.workspaceSetupCommand;
      const value = raw === null ? null : raw.trim() === "" ? null : raw.trim();
      try {
        const updated = service.updateField(request.params.project_id, {
          workspaceSetupCommand: value,
        });
        return sendJsonScalar(reply, updated.workspaceSetupCommand ?? null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.put(
    "/api/v1/projects/:project_id/naming_pattern",
    {
      schema: {
        params: ProjectIdParamsSchema,
        body: z.object({ namingPattern: z.string() }),
        response: { 200: z.string().nullable(), ...errorResponses },
      },
    },
    async (request, reply) => {
      const trimmed = request.body.namingPattern.trim();
      const value = trimmed === "" ? null : trimmed;
      try {
        const updated = service.updateField(request.params.project_id, {
          namingPattern: value,
        });
        return sendJsonScalar(reply, updated.namingPattern ?? null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/projects/:project_id/files_and_folders",
    {
      schema: {
        params: ProjectIdParamsSchema,
        querystring: z.object({
          directory: z.string().default(""),
          filter: z.string().default(""),
          workspace_id: z.string().optional(),
        }),
        response: { 200: z.array(z.string()), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return filesAndFolders(
          request.params.project_id,
          request.query.directory,
          request.query.filter,
          request.query.workspace_id ?? null,
        );
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/projects/:project_id/current_branch",
    {
      schema: {
        params: ProjectIdParamsSchema,
        response: {
          200: z.object({ currentBranch: z.string() }),
          ...errorResponses,
        },
      },
    },
    async (request, reply) => {
      try {
        return {
          currentBranch: await getCurrentBranch(request.params.project_id),
        };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/projects/:project_id/branch-exists",
    {
      schema: {
        params: ProjectIdParamsSchema,
        querystring: z.object({ name: z.string() }),
        response: { 200: z.object({ exists: z.boolean() }), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return {
          exists: await checkBranchExists(
            request.params.project_id,
            request.query.name,
          ),
        };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/projects/:project_id/repo_info",
    {
      schema: {
        params: ProjectIdParamsSchema,
        response: { 200: RepoInfoSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return await getRepoInfo(request.params.project_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );
}
