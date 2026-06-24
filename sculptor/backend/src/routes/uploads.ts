import { randomUUID } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { uploadsDir } from "~/config/sculptor_folder";
import { spawnBackgroundProcess } from "~/environment/process";

// Upload + open-path endpoints (web/app.py). Uploads land in internal/uploads/
// (Task 1.5) so migrated files resolve (RW-DATA-5). upload-diagnostics is the
// one upload that delegates to the S3 service (Task 7.8) and is wired there.

const MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024; // 20MB (REQ-NFR-051)

function expandUser(input: string): string {
  return input === "~" || input.startsWith("~/")
    ? path.join(os.homedir(), input.slice(1))
    : input;
}

// Best-effort external-app opener (web/open_with.py). Fire-and-forget; the
// detailed availability probing is out of scope for the rewrite's first cut.
function openInApp(
  app: string,
  target: string,
): { success: boolean; errorMessage?: string | null } {
  const isMac = process.platform === "darwin";
  try {
    if (app === "finder") {
      spawnBackgroundProcess(
        isMac ? ["open", "-R", target] : ["xdg-open", path.dirname(target)],
      );
    } else if (app === "vscode") {
      spawnBackgroundProcess(["code", target]);
    } else if (app === "cursor") {
      spawnBackgroundProcess(["cursor", target]);
    } else {
      return { success: false, errorMessage: `Unknown app: ${app}` };
    }
    return { success: true, errorMessage: null };
  } catch (error) {
    return {
      success: false,
      errorMessage: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function registerUploadRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  app.post("/api/v1/upload-file", async (request, reply: FastifyReply) => {
    const data = await request.file({
      limits: { fileSize: MAX_UPLOAD_SIZE_BYTES },
    });
    if (data === undefined) {
      return reply.code(400).send({ detail: "No file provided" });
    }
    const buffer = await data.toBuffer();
    if (data.file.truncated) {
      return reply
        .code(413)
        .send({ detail: "File exceeds maximum size of 20MB" });
    }
    const ext = path.extname(data.filename ?? "");
    const fileId = `${randomUUID()}${ext}`;
    const dir = uploadsDir();
    mkdirSync(dir, { recursive: true });
    writeFileSync(path.join(dir, fileId), buffer);
    return reply.code(200).send({ fileId });
  });

  app.get(
    "/api/v1/uploaded-file/:file_id",
    async (request, reply: FastifyReply) => {
      const { file_id: fileId } = request.params as { file_id: string };
      const dir = path.resolve(uploadsDir());
      const filePath = path.resolve(dir, fileId);
      if (!filePath.startsWith(dir + path.sep)) {
        return reply.code(400).send({ detail: "Invalid file_id" });
      }
      if (!existsSync(filePath) || !statSync(filePath).isFile()) {
        return reply.code(404).send({ detail: "File not found" });
      }
      return reply.code(200).send(readFileSync(filePath));
    },
  );

  typed.post(
    "/api/v1/open-path-in-app",
    {
      schema: {
        body: z.object({ path: z.string(), app: z.string() }),
        response: {
          200: z.object({
            success: z.boolean(),
            errorMessage: z.string().nullable().optional(),
          }),
        },
      },
    },
    async (request) =>
      openInApp(request.body.app, expandUser(request.body.path)),
  );
}
