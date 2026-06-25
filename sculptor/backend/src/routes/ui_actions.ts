import { existsSync } from "node:fs";
import path from "node:path";

import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getWorkspace } from "~/db/repositories";
import { WorkspaceError } from "~/services/workspace";
import { publishOpenFile, publishWebviewCommand } from "~/services/ui_actions";

// UI-action routes (web/app.py): open-file + webview navigate/refresh. Each
// succeeds by emitting a stream event the frontend reacts to; the HTTP response
// is 204 No Content.

// detail is a plain string for webview commands but a {code, message} object
// for open-file, whose codes the sculpt CLI maps to distinct exit codes
// (workspace_not_open→3, file_not_found/file_not_absolute→4).
const CodedDetailSchema = z.object({ code: z.string(), message: z.string() });
const ErrorResponseSchema = z.object({
  detail: z.union([z.string(), CodedDetailSchema]),
});
const errorResponses = {
  400: ErrorResponseSchema,
  404: ErrorResponseSchema,
  409: ErrorResponseSchema,
};
const WorkspaceIdParamsSchema = z.object({ workspace_id: z.string() });

// An error carrying the structured {code, message} detail the CLI dispatches on.
class CodedError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof CodedError) {
    return reply
      .code(error.status)
      .send({ detail: { code: error.code, message: error.message } });
  }
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

// Resolve a CLI-provided path to a host-readable file (app.py
// _resolve_open_file_target). The path must be absolute and must exist (in the
// workspace checkout or anywhere else the host can read — open-file is allowed
// to surface files outside the clone). No traversal rejection.
function resolveOpenFileTarget(filePath: string): string {
  if (!path.isAbsolute(filePath)) {
    throw new CodedError(
      400,
      "file_not_absolute",
      `path must be absolute: ${filePath}`,
    );
  }
  if (!existsSync(filePath)) {
    throw new CodedError(404, "file_not_found", filePath);
  }
  return filePath;
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
          throw new CodedError(
            404,
            "workspace_not_found",
            `workspace ${request.params.workspace_id} not found`,
          );
        }
        if (!row.isOpen) {
          throw new CodedError(
            409,
            "workspace_not_open",
            `workspace ${request.params.workspace_id} is not open; cannot show files in a closed workspace`,
          );
        }
        const resolved = resolveOpenFileTarget(request.body.filePath);
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
