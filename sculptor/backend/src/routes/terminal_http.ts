import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getAgent, updateAgent } from "~/db/repositories";
import { getTerminalManager } from "~/terminal/instance";
import { listRegistrations } from "~/services/terminal_agent_registry/registry";

// Terminal HTTP endpoints (web/app.py): automated input to a terminal agent,
// the terminal-agent signal event API, terminal close, and the registrations
// listing. NOTE: terminal-agent-registrations reads the registry built in Task
// 7.5; until then it reports an empty list.

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = { 404: ErrorResponseSchema };

const SESSION_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;

function notFound(reply: FastifyReply, detail: string): FastifyReply {
  return reply.code(404).send({ detail });
}

export async function registerTerminalHttpRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  typed.post(
    "/api/v1/agents/:agent_id/terminal/input",
    {
      schema: {
        params: z.object({ agent_id: z.string() }),
        body: z.object({ text: z.string(), submit: z.boolean().default(true) }),
        response: { 204: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      const agent = getAgent(getOrm(), request.params.agent_id);
      if (agent === undefined || agent.isDeleted) {
        return notFound(reply, "Agent not found");
      }
      const pty = getTerminalManager().getAgentTerminal(
        request.params.agent_id,
      );
      if (pty === undefined) {
        return notFound(reply, "Terminal not found");
      }
      pty.write(
        request.body.submit ? `${request.body.text}\n` : request.body.text,
      );
      return reply.code(204).send(null);
    },
  );

  // The local HTTP event API terminal-agent integrations post to. The rich
  // status/files-changed handling lands with the terminal-agent service (Task
  // 7.5); here we persist the session id (for resume) and accept the rest.
  typed.post(
    "/api/v1/agents/:agent_id/signal",
    {
      schema: {
        params: z.object({ agent_id: z.string() }),
        body: z.object({
          event: z.string(),
          sessionId: z.string().nullable().optional(),
        }),
        response: { 204: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      const orm = getOrm();
      const agent = getAgent(orm, request.params.agent_id);
      if (agent === undefined || agent.isDeleted) {
        return notFound(reply, "Agent not found");
      }
      if (
        request.body.event === "session-id" &&
        request.body.sessionId != null &&
        SESSION_ID_PATTERN.test(request.body.sessionId)
      ) {
        updateAgent(orm, request.params.agent_id, {
          terminalSessionId: request.body.sessionId,
        });
      }
      return reply.code(204).send(null);
    },
  );

  typed.delete(
    "/api/v1/workspaces/:workspace_id/terminal/:index",
    {
      schema: {
        params: z.object({ workspace_id: z.string(), index: z.string() }),
        response: { 200: z.null() },
      },
    },
    async (request, reply) => {
      getTerminalManager().closeTerminal(
        Number.parseInt(request.params.index, 10),
      );
      return reply.code(200).send(null);
    },
  );

  typed.get(
    "/api/v1/terminal-agent-registrations",
    {
      schema: {
        response: {
          200: z.object({
            registrations: z.array(
              z.object({
                registrationId: z.string(),
                displayName: z.string(),
                launchCommand: z.string(),
                resumeCommandTemplate: z.string().nullable(),
                acceptsAutomatedPrompts: z.boolean(),
              }),
            ),
          }),
        },
      },
    },
    async () => {
      // Re-read on demand (REQ-INT-030) — no process-lifetime cache.
      return { registrations: listRegistrations() };
    },
  );
}
