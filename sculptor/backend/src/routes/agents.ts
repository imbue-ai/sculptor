import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getAgent, markAgentRead, updateAgent } from "~/db/repositories";
import { eventBus } from "~/events";
import {
  AgentError,
  agentViewWire,
  getAgentService,
  type AgentTypeName,
} from "~/services/agent";
import { getWorkspaceService, WorkspaceError } from "~/services/workspace";

// Agent lifecycle endpoints (web/app.py). camelCase wire (RW-API-3). Includes
// the legacy POST /projects/{id}/tasks create (deferred here from Task 6.3).

const AgentViewSchema = z.object({
  objectType: z.literal("CodingAgentTaskView"),
  taskId: z.string(),
  workspaceId: z.string().nullable(),
  projectId: z.string(),
  status: z.string(),
  title: z.string().nullable(),
  goal: z.string(),
  model: z.string().nullable(),
  currentActivity: z.string().nullable(),
  lastActivity: z.string().nullable(),
  taskCompleted: z.number().int(),
  taskTotal: z.number().int(),
  currentTaskSubject: z.string().nullable(),
  waitingDetail: z.string().nullable(),
  errorDetail: z.string().nullable(),
});

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = {
  400: ErrorResponseSchema,
  404: ErrorResponseSchema,
  409: ErrorResponseSchema,
  422: ErrorResponseSchema,
};

const agentTypeSchema = z
  .enum(["claude", "pi", "terminal", "registered"])
  .default("claude");

const CreateAgentSchema = z.object({
  prompt: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  interface: z.string().default("terminal"),
  files: z.array(z.string()).default([]),
  name: z.string().nullable().optional(),
  enterPlanMode: z.boolean().default(false),
  fastMode: z.boolean().default(false),
  effort: z.string().default("xhigh"),
  sentVia: z.string().nullable().optional(),
  agentType: agentTypeSchema,
  registrationId: z.string().nullable().optional(),
});

const WorkspaceAgentParamsSchema = z.object({
  workspace_id: z.string(),
  agent_id: z.string(),
});
const WorkspaceIdParamsSchema = z.object({ workspace_id: z.string() });

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof AgentError || error instanceof WorkspaceError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  throw error;
}

function toCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_match, char: string) =>
    char.toUpperCase(),
  );
}
// Artifacts are stored snake_case on disk; the wire is camelCase. The only
// data-keyed map (DiffArtifact.file_errors) holds file paths, so its subtree is
// passed through verbatim.
function camelizeArtifact(value: unknown, opaque = false): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => camelizeArtifact(item, opaque));
  }
  if (value !== null && typeof value === "object") {
    if (opaque) {
      return value;
    }
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value)) {
      out[toCamel(key)] = camelizeArtifact(inner, key === "file_errors");
    }
    return out;
  }
  return value;
}

export async function registerAgentRoutes(app: FastifyInstance): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  const service = getAgentService();

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: CreateAgentSchema,
        response: { 200: AgentViewSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return await service.create(request.params.workspace_id, request.body);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id/agents",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: z.array(AgentViewSchema), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return service.list(request.params.workspace_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/agents/by-prefix/:prefix",
    {
      schema: {
        params: z.object({ prefix: z.string() }),
        response: { 200: z.object({ agentId: z.string() }), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        return { agentId: service.resolveByPrefix(request.params.prefix) };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.delete(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id",
    {
      schema: {
        params: WorkspaceAgentParamsSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.delete(request.params.agent_id);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/restore",
    {
      schema: {
        params: WorkspaceAgentParamsSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.restore(request.params.agent_id);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/diagnostics",
    {
      schema: {
        params: WorkspaceAgentParamsSchema,
        response: {
          200: z.object({
            sessionId: z.string().nullable(),
            transcriptFilePath: z.string().nullable(),
            sculptorTranscriptFilePath: z.string().nullable(),
          }),
          ...errorResponses,
        },
      },
    },
    async (request, reply) => {
      try {
        return service.diagnostics(request.params.agent_id);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/artifacts/:artifact_name",
    {
      schema: {
        params: z.object({
          workspace_id: z.string(),
          agent_id: z.string(),
          artifact_name: z.string(),
        }),
        response: {
          200: z.record(z.string(), z.unknown()),
          ...errorResponses,
          500: ErrorResponseSchema,
        },
      },
    },
    async (request, reply) => {
      try {
        return camelizeArtifact(
          service.artifact(
            request.params.agent_id,
            request.params.artifact_name,
          ),
        ) as Record<string, unknown>;
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  // Legacy create-under-project (web/app.py:476). Uses an existing workspace or
  // creates an implicit IN_PLACE one, then creates the agent.
  typed.post(
    "/api/v1/projects/:project_id/tasks",
    {
      schema: {
        params: z.object({ project_id: z.string() }),
        body: z.object({
          prompt: z.string(),
          interface: z.string().default("terminal"),
          model: z.string(),
          files: z.array(z.string()).default([]),
          initializationStrategy: z
            .enum(["IN_PLACE", "CLONE", "WORKTREE"])
            .default("IN_PLACE"),
          name: z.string().nullable().optional(),
          sourceBranch: z.string().nullable().optional(),
          workspaceId: z.string().nullable().optional(),
          enterPlanMode: z.boolean().default(false),
          fastMode: z.boolean().default(false),
          effort: z.string().default("xhigh"),
          sentVia: z.string().nullable().optional(),
          agentType: agentTypeSchema,
        }),
        response: { 200: AgentViewSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        let workspaceId = request.body.workspaceId ?? null;
        if (workspaceId === null) {
          const created = await getWorkspaceService().create({
            projectId: request.params.project_id,
            initializationStrategy: request.body.initializationStrategy,
            sourceBranch: request.body.sourceBranch ?? null,
            requestedBranchName:
              request.body.initializationStrategy === "WORKTREE"
                ? request.body.name
                : null,
          });
          workspaceId = created.objectId;
        }
        return await service.create(workspaceId, {
          prompt: request.body.prompt,
          model: request.body.model,
          files: request.body.files,
          name: request.body.name,
          enterPlanMode: request.body.enterPlanMode,
          fastMode: request.body.fastMode,
          effort: request.body.effort,
          sentVia: request.body.sentVia,
          agentType: request.body.agentType as AgentTypeName,
        });
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  // PATCH an agent's title (rename) / read state. The codegen contract for these
  // operations is the snapshot overlay (Task 9.4); the agent_status event
  // refreshes the projection. Each returns the updated CodingAgentTaskView.
  const refreshedView = (
    reply: FastifyReply,
    agentId: string,
  ): ReturnType<typeof agentViewWire> | FastifyReply => {
    const updated = getAgent(getOrm(), agentId);
    if (updated === undefined) {
      return reply.code(404).send({ detail: "Agent not found" });
    }
    eventBus.publish({ kind: "agent_status", agentId });
    return agentViewWire(updated);
  };

  typed.patch(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id",
    {
      schema: {
        params: WorkspaceAgentParamsSchema,
        body: z.object({ title: z.string() }),
        response: { 200: AgentViewSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      const agent = getAgent(getOrm(), request.params.agent_id);
      if (agent === undefined || agent.isDeleted) {
        return reply.code(404).send({ detail: "Agent not found" });
      }
      updateAgent(getOrm(), request.params.agent_id, {
        title: request.body.title,
      });
      return refreshedView(reply, request.params.agent_id);
    },
  );

  typed.patch(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/mark-read",
    {
      schema: {
        params: WorkspaceAgentParamsSchema,
        response: { 200: AgentViewSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      const agent = getAgent(getOrm(), request.params.agent_id);
      if (agent === undefined || agent.isDeleted) {
        return reply.code(404).send({ detail: "Agent not found" });
      }
      markAgentRead(getOrm(), request.params.agent_id);
      return refreshedView(reply, request.params.agent_id);
    },
  );

  typed.patch(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/mark-unread",
    {
      schema: {
        params: WorkspaceAgentParamsSchema,
        response: { 200: AgentViewSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      const agent = getAgent(getOrm(), request.params.agent_id);
      if (agent === undefined || agent.isDeleted) {
        return reply.code(404).send({ detail: "Agent not found" });
      }
      updateAgent(getOrm(), request.params.agent_id, { lastReadAt: null });
      return refreshedView(reply, request.params.agent_id);
    },
  );
}
