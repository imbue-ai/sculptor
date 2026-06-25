import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { setWorkspaceDiffStatus, updateWorkspace } from "~/db/repositories";
import { workspaceInitializationStrategySchema } from "~/db/schema/enums";
import { eventBus } from "~/events";
import {
  getWorkspaceService,
  previewWorkspaceBranchName,
  WorkspaceError,
} from "~/services/workspace";

// Workspace lifecycle endpoints (web/app.py). camelCase wire shapes (RW-API-3).

const SetupSnapshotSchema = z.object({
  status: z.enum([
    "not_configured",
    "pending",
    "running",
    "succeeded",
    "failed",
    "legacy",
  ]),
  runId: z.string().nullable(),
  exitCode: z.number().int().nullable(),
  startedAt: z.number().nullable(),
  finishedAt: z.number().nullable(),
  logTruncated: z.boolean(),
});

const WorkspaceResponseSchema = z.object({
  objectId: z.string(),
  projectId: z.string(),
  description: z.string(),
  initializationStrategy: workspaceInitializationStrategySchema,
  sourceBranch: z.string().nullable(),
  targetBranch: z.string().nullable(),
  requestedBranchName: z.string().nullable(),
  environmentId: z.string().nullable(),
  isDeleted: z.boolean(),
  isOpen: z.boolean(),
  createdAt: z.string(),
  workspaceSetupCommand: z.string().nullable(),
  setup: SetupSnapshotSchema.nullable(),
});

const RecentWorkspaceSchema = z.object({
  objectId: z.string(),
  projectId: z.string(),
  description: z.string(),
  initializationStrategy: workspaceInitializationStrategySchema,
  sourceBranch: z.string().nullable(),
  isDeleted: z.boolean(),
  createdAt: z.string(),
  projectName: z.string(),
  agentCount: z.number().int(),
  isOpen: z.boolean(),
  lastActivityAt: z.string().nullable(),
});

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = {
  400: ErrorResponseSchema,
  404: ErrorResponseSchema,
  409: ErrorResponseSchema,
  422: ErrorResponseSchema,
};

const CreateWorkspaceSchema = z.object({
  projectId: z.string(),
  initializationStrategy: workspaceInitializationStrategySchema,
  sourceBranch: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  requestedBranchName: z.string().nullable().optional(),
  targetBranch: z.string().nullable().optional(),
});

const WorkspaceIdParamsSchema = z.object({ workspace_id: z.string() });

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof WorkspaceError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  throw error;
}

export async function registerWorkspaceRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  const service = getWorkspaceService();

  typed.post(
    "/api/v1/workspaces",
    {
      schema: {
        body: CreateWorkspaceSchema,
        response: { 200: WorkspaceResponseSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return await service.create(request.body);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/preview-branch-name",
    {
      schema: {
        querystring: z.object({
          project_id: z.string(),
          workspace_name: z.string().default(""),
          mode: workspaceInitializationStrategySchema.default("WORKTREE"),
        }),
        response: {
          200: z.object({ branchName: z.string() }),
          ...errorResponses,
        },
      },
    },
    async (request, reply) => {
      try {
        const branchName = await previewWorkspaceBranchName(
          request.query.project_id,
          request.query.workspace_name,
          request.query.mode,
        );
        return { branchName };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/recent",
    {
      schema: {
        response: {
          200: z.object({ workspaces: z.array(RecentWorkspaceSchema) }),
        },
      },
    },
    async () => ({ workspaces: service.recent() }),
  );

  typed.post(
    "/api/v1/workspaces/batch-update-open-state",
    {
      schema: {
        body: z.object({
          workspaceIds: z.array(z.string()),
          isOpen: z.boolean(),
        }),
        response: { 200: z.null() },
      },
    },
    async (request, reply) => {
      service.batchUpdateOpenState(
        request.body.workspaceIds,
        request.body.isOpen,
      );
      return reply.code(200).send(null);
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/setup/cancel",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: SetupSnapshotSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return service.cancelSetup(request.params.workspace_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/setup/rerun",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: SetupSnapshotSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return service.rerunSetup(request.params.workspace_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: WorkspaceResponseSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return service.get(request.params.workspace_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/projects/:project_id/workspaces",
    {
      schema: {
        params: z.object({ project_id: z.string() }),
        response: { 200: z.array(WorkspaceResponseSchema) },
      },
    },
    async (request) => service.listByProject(request.params.project_id),
  );

  // PATCH a workspace's mutable fields (description / target branch / open
  // state). The codegen contract for this operation is the snapshot overlay
  // (Task 9.4); the data_model_change refreshes the projection.
  typed.patch(
    "/api/v1/workspaces/:workspace_id",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        // Accept camelCase (the generated client / frontend) and snake_case
        // (Pydantic field names, which the Python models accept via
        // populate_by_name) for each field.
        body: z.object({
          description: z.string().nullable().optional(),
          targetBranch: z.string().nullable().optional(),
          target_branch: z.string().nullable().optional(),
          isOpen: z.boolean().nullable().optional(),
          is_open: z.boolean().nullable().optional(),
        }),
        response: { 200: WorkspaceResponseSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        const patch: Record<string, unknown> = {};
        if (request.body.description != null) {
          patch.description = request.body.description;
        }
        const targetBranch =
          request.body.targetBranch !== undefined
            ? request.body.targetBranch
            : request.body.target_branch;
        if (targetBranch !== undefined) {
          patch.targetBranch = targetBranch;
        }
        const isOpen = request.body.isOpen ?? request.body.is_open;
        if (isOpen != null) {
          patch.isOpen = isOpen;
        }
        if (Object.keys(patch).length > 0) {
          updateWorkspace(getOrm(), request.params.workspace_id, patch);
          // Changing the target branch changes what the diff is computed
          // against, so recompute it (web/app.py refresh_workspace_diff). Bumping
          // the diff marker invalidates the frontend's git-derived queries.
          if (targetBranch !== undefined) {
            setWorkspaceDiffStatus(
              getOrm(),
              request.params.workspace_id,
              "READY",
            );
          }
          eventBus.publish({
            kind: "data_model_change",
            changedEntities: [
              { type: "workspace", id: request.params.workspace_id },
            ],
          });
        }
        return service.get(request.params.workspace_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.delete(
    "/api/v1/workspaces/:workspace_id",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.delete(request.params.workspace_id);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );
}
