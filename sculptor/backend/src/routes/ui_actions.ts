import path from "node:path";

import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getWorkspace } from "~/db/repositories";
import {
  getWorkspaceWorkingDirectory,
  WorkspaceError,
} from "~/services/workspace";
import { publishOpenFile, publishWebviewCommand } from "~/services/ui_actions";

// UI-action routes (web/app.py): open-file + webview navigate/refresh. Each
// succeeds by emitting a stream event the frontend reacts to; the HTTP response
// is 204 No Content.

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = {
  400: ErrorResponseSchema,
  404: ErrorResponseSchema,
  409: ErrorResponseSchema,
};
const WorkspaceIdParamsSchema = z.object({ workspace_id: z.string() });

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof WorkspaceError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  throw error;
}

// Workspace must exist; the webview commands additionally require it to be open
// (you cannot drive a closed workspace's browser panel).
function requireOpenWorkspace(workspaceId: string): void {
  const row = getWorkspace(getOrm(), workspaceId);
  if (row === undefined || row.isDeleted) {
    throw new WorkspaceError(404, `Workspace ${workspaceId} not found`);
  }
  if (!row.isOpen) {
    throw new WorkspaceError(
      409,
      `Workspace ${workspaceId} is not open; cannot drive its webview`,
    );
  }
}

// Resolve a workspace-relative path, rejecting traversal outside the tree.
function resolveWithinWorkspace(workspaceId: string, filePath: string): string {
  const workingDir = path.resolve(getWorkspaceWorkingDirectory(workspaceId));
  const resolved = path.resolve(workingDir, filePath);
  if (
    resolved !== workingDir &&
    !resolved.startsWith(`${workingDir}${path.sep}`)
  ) {
    throw new WorkspaceError(400, "Path traversal not allowed");
  }
  return resolved;
}

export async function registerUiActionRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  typed.post(
    "/api/v1/workspaces/:workspace_id/ui/open-file",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: z.object({
          filePath: z.string(),
          mode: z.enum(["auto", "diff", "file"]),
        }),
        response: { 204: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        const row = getWorkspace(getOrm(), request.params.workspace_id);
        if (row === undefined || row.isDeleted) {
          return reply
            .code(404)
            .send({
              detail: `Workspace ${request.params.workspace_id} not found`,
            });
        }
        const resolved = resolveWithinWorkspace(
          request.params.workspace_id,
          request.body.filePath,
        );
        publishOpenFile(
          request.params.workspace_id,
          resolved,
          request.body.mode,
        );
        return reply.code(204).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/ui/webview/navigate",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: z.object({ url: z.string().min(1) }),
        response: { 204: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        requireOpenWorkspace(request.params.workspace_id);
        publishWebviewCommand(
          request.params.workspace_id,
          "navigate",
          request.body.url,
        );
        return reply.code(204).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/ui/webview/refresh",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 204: z.null(), ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        requireOpenWorkspace(request.params.workspace_id);
        publishWebviewCommand(request.params.workspace_id, "refresh", null);
        return reply.code(204).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );
}
