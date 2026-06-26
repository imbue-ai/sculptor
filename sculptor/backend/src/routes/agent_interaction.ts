import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getAgent } from "~/db/repositories";
import { AgentError, getAgentService } from "~/services/agent";
import { getBtwService } from "~/services/btw/btw";

// Agent-interaction endpoints (web/app.py): send message, answer question,
// clear context, interrupt, set model, delete a message. Effects stream back
// over /stream/ws. The /btw side-question endpoint delegates to the btw service.

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = {
  400: ErrorResponseSchema,
  404: ErrorResponseSchema,
  409: ErrorResponseSchema,
  422: ErrorResponseSchema,
};
const AgentParamsSchema = z.object({
  workspace_id: z.string(),
  agent_id: z.string(),
});

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof AgentError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  throw error;
}

export async function registerAgentInteractionRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  const service = getAgentService();

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/messages",
    {
      schema: {
        params: AgentParamsSchema,
        body: z.object({
          message: z.string(),
          model: z.string(),
          files: z.array(z.string()).default([]),
          enterPlanMode: z.boolean().default(false),
          exitPlanMode: z.boolean().default(false),
          fastMode: z.boolean().default(false),
          effort: z.string().default("xhigh"),
          sentVia: z.string().nullable().optional(),
        }),
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.sendMessage(request.params.agent_id, request.body);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/answer_question",
    {
      schema: {
        params: AgentParamsSchema,
        body: z.object({
          answers: z.record(z.string(), z.string()),
          notes: z.record(z.string(), z.string()).default({}),
          questionData: z.record(z.string(), z.unknown()),
          toolUseId: z.string(),
          model: z.string(),
        }),
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.answerQuestion(request.params.agent_id, {
          answers: request.body.answers,
          notes: request.body.notes,
          questionData: request.body.questionData,
          toolUseId: request.body.toolUseId,
        });
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/clear_context",
    {
      schema: {
        params: AgentParamsSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.clearContext(request.params.agent_id);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/interrupt",
    {
      schema: {
        params: AgentParamsSchema,
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.interrupt(request.params.agent_id);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/set_model",
    {
      schema: {
        params: AgentParamsSchema,
        body: z.object({ provider: z.string(), modelId: z.string() }),
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.setModel(
          request.params.agent_id,
          request.body.provider,
          request.body.modelId,
        );
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.delete(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/messages/:message_id",
    {
      schema: {
        params: z.object({
          workspace_id: z.string(),
          agent_id: z.string(),
          message_id: z.string(),
        }),
        response: { 200: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        service.deleteMessage(
          request.params.agent_id,
          request.params.message_id,
        );
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  // POST /btw — a read-only side-question. Fire-and-forget: the
  // answer streams back via btw_update on /stream/ws. It never mutates the
  // agent's messages or run_state.
  typed.post(
    "/api/v1/workspaces/:workspace_id/agents/:agent_id/btw",
    {
      schema: {
        params: AgentParamsSchema,
        body: z.object({ question: z.string(), requestId: z.string() }),
        response: { 204: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      const agent = getAgent(getOrm(), request.params.agent_id);
      if (agent === undefined || agent.isDeleted) {
        return reply.code(404).send({ detail: "Agent not found" });
      }
      // A never-started agent has no Claude session to fork — no init is coming,
      // so fast-fail with 409 (the frontend toasts "/btw is unavailable until
      // you've sent a message"). A started agent's session is awaited in the
      // service. Mirrors btw_service/api.py's is_main_agent_started branch.
      if (agent.runState === "QUEUED" && agent.claudeSessionId === null) {
        return reply
          .code(409)
          .send({ detail: "No active Claude session for this agent" });
      }
      getBtwService().runBtwForAgent(
        request.params.workspace_id,
        request.params.agent_id,
        request.body.requestId,
        request.body.question,
      );
      return reply.code(204).send(null);
    },
  );
}
