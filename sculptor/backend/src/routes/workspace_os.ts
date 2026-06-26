import { existsSync } from "node:fs";
import path from "node:path";

import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getWorkspace } from "~/db/repositories";
import { spawnBackgroundProcess } from "~/environment/process";
import { discardFile } from "~/git";
import {
  getWorkspaceWorkingDirectory,
  WorkspaceError,
} from "~/services/workspace";

// open-in-os + discard-file (web/app.py). open-in-os shells out to the platform
// file opener (open / xdg-open); discard-file restores a file via git.

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = { 400: ErrorResponseSchema, 404: ErrorResponseSchema };
const WorkspaceIdParamsSchema = z.object({ workspace_id: z.string() });

const GitOperationResultSchema = z.object({
  success: z.boolean(),
  stdout: z.string(),
  stderr: z.string(),
});

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof WorkspaceError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  throw error;
}

// Platform-aware open (web/open_with.py). `open`/`xdg-open` a file or reveal it
// in the containing folder. Fire-and-forget: it launches a GUI app.
function osOpen(
  target: string,
  action: "open_file" | "open_containing_folder",
): void {
  if (process.platform === "darwin") {
    spawnBackgroundProcess(
      action === "open_file" ? ["open", target] : ["open", "-R", target],
    );
  } else if (process.platform === "linux") {
    const argument = action === "open_file" ? target : path.dirname(target);
    spawnBackgroundProcess(["xdg-open", argument]);
  } else {
    throw new WorkspaceError(400, `Unsupported platform: ${process.platform}`);
  }
}

export async function registerWorkspaceOsRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  typed.post(
    "/api/v1/workspaces/:workspace_id/open-in-os",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: z.object({
          path: z.string(),
          action: z.enum(["open_file", "open_containing_folder"]),
        }),
        response: { 200: z.null(), ...errorResponses },
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
        const workingDir = path.resolve(
          getWorkspaceWorkingDirectory(request.params.workspace_id),
        );
        const absPath = path.resolve(workingDir, request.body.path);
        if (
          absPath !== workingDir &&
          !absPath.startsWith(`${workingDir}${path.sep}`)
        ) {
          return reply.code(400).send({ detail: "Path traversal not allowed" });
        }
        if (!existsSync(absPath)) {
          return reply.code(404).send({ detail: "File not found" });
        }
        osOpen(absPath, request.body.action);
        return reply.code(200).send(null);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/discard-file",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: z.object({ filePath: z.string() }),
        response: {
          200: z.object({ result: GitOperationResultSchema }),
          ...errorResponses,
        },
      },
    },
    async (request, reply) => {
      try {
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        await discardFile(workingDir, request.body.filePath);
        return { result: { success: true, stdout: "", stderr: "" } };
      } catch (error) {
        if (error instanceof WorkspaceError) {
          return handleError(error, reply);
        }
        return {
          result: {
            success: false,
            stdout: "",
            stderr: error instanceof Error ? error.message : String(error),
          },
        };
      }
    },
  );
}
