import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import type { FastifyInstance, FastifyReply } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getWorkspace } from "~/db/repositories";
import { getOrm } from "~/db/orm";
import {
  commitDiff,
  InvalidCommitError,
  listCommits,
  readFileAtRef,
  runGit,
  workspaceDiff,
} from "~/git";
import {
  getWorkspaceWorkingDirectory,
  WorkspaceError,
  type WorkspaceResponseWire,
} from "~/services/workspace";

// Read-side workspace endpoints (web/app.py): diff, commits, commit-diff,
// read-file, read-file-at-ref, files. They surface the git layer (Task 3.3)
// over HTTP. The git layer returns snake_case internal shapes; the wire is
// camelCase (RW-API-3), converted here.

const DiffArtifactSchema = z.object({
  objectType: z.literal("DiffArtifact"),
  uncommittedDiff: z.string(),
  targetBranchDiff: z.string(),
  targetBranchMergeBase: z.string(),
  // Keys are file paths (data) — left verbatim.
  fileErrors: z.record(z.string(), z.string()),
});

const CommitFileInfoSchema = z.object({
  path: z.string(),
  status: z.enum(["M", "A", "D", "R"]),
  oldPath: z.string().nullable(),
  additions: z.number().int(),
  deletions: z.number().int(),
});

const CommitInfoSchema = z.object({
  hash: z.string(),
  shortHash: z.string(),
  message: z.string(),
  authorName: z.string(),
  timestamp: z.string(),
  parentHashes: z.array(z.string()),
  files: z.array(CommitFileInfoSchema),
});

const CommitHistorySchema = z.object({
  commits: z.array(CommitInfoSchema),
  forkPoint: z.string().nullable(),
});

const CommitDiffSchema = z.object({
  diff: z.string(),
  commitHash: z.string(),
  parentHash: z.string().nullable(),
});

const ReadFileResponseSchema = z.object({
  content: z.string(),
  encoding: z.enum(["utf-8", "base64"]),
});

const WorkspaceFileListSchema = z.object({
  files: z.array(
    z.object({ path: z.string(), type: z.enum(["directory", "file"]) }),
  ),
});

const ErrorResponseSchema = z.object({ detail: z.string() });
const errorResponses = { 400: ErrorResponseSchema, 404: ErrorResponseSchema };

const WorkspaceIdParamsSchema = z.object({ workspace_id: z.string() });

// --- snake -> camel converters (git layer is snake_case internally) ---------

function diffArtifactToWire(
  diff: Awaited<ReturnType<typeof workspaceDiff>>,
): z.infer<typeof DiffArtifactSchema> {
  return {
    objectType: "DiffArtifact",
    uncommittedDiff: diff.uncommitted_diff,
    targetBranchDiff: diff.target_branch_diff,
    targetBranchMergeBase: diff.target_branch_merge_base,
    fileErrors: diff.file_errors,
  };
}

function commitHistoryToWire(
  history: Awaited<ReturnType<typeof listCommits>>,
): z.infer<typeof CommitHistorySchema> {
  return {
    commits: history.commits.map((commit) => ({
      hash: commit.hash,
      shortHash: commit.short_hash,
      message: commit.message,
      authorName: commit.author_name,
      timestamp: commit.timestamp,
      parentHashes: commit.parent_hashes,
      files: commit.files.map((file) => ({
        path: file.path,
        status: file.status,
        oldPath: file.old_path,
        additions: file.additions,
        deletions: file.deletions,
      })),
    })),
    forkPoint: history.fork_point,
  };
}

function handleError(error: unknown, reply: FastifyReply): FastifyReply {
  if (error instanceof WorkspaceError) {
    return reply.code(error.status).send({ detail: error.message });
  }
  if (error instanceof InvalidCommitError) {
    return reply.code(400).send({ detail: error.message });
  }
  throw error;
}

function requireWorkspace(workspaceId: string): WorkspaceResponseWire | never {
  const row = getWorkspace(getOrm(), workspaceId);
  if (row === undefined || row.isDeleted) {
    throw new WorkspaceError(404, `Workspace ${workspaceId} not found`);
  }
  // Only the target branch / source hash are needed by the read paths.
  return {
    objectId: row.objectId,
    projectId: row.projectId,
    description: row.description,
    initializationStrategy: row.initializationStrategy,
    sourceBranch: row.sourceBranch ?? null,
    targetBranch: row.targetBranch ?? null,
    requestedBranchName: row.requestedBranchName ?? null,
    environmentId: row.environmentId ?? null,
    isDeleted: row.isDeleted,
    isOpen: row.isOpen,
    createdAt: row.createdAt,
    workspaceSetupCommand: row.setupCommand ?? null,
    setup: null,
  };
}

// Read a file, returning utf-8 text or base64 (binary). Mirrors the
// UnicodeDecodeError fallback in workspace_read_file.
function readFileContent(filePath: string): {
  content: string;
  encoding: "utf-8" | "base64";
} {
  const buffer = readFileSync(filePath);
  try {
    const content = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    return { content, encoding: "utf-8" };
  } catch {
    return { content: buffer.toString("base64"), encoding: "base64" };
  }
}

export async function registerWorkspaceFileRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();

  typed.get(
    "/api/v1/workspaces/:workspace_id/diff",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        querystring: z.object({
          // Accepted for API parity; the diff is always recomputed.
          force_refresh: z.string().default("false"),
          context_lines: z.coerce.number().int().default(3),
          scope: z.string().default("uncommitted"),
        }),
        response: {
          200: z.object({ diff: DiffArtifactSchema }),
          ...errorResponses,
        },
      },
    },
    async (request, reply) => {
      try {
        const workspace = requireWorkspace(request.params.workspace_id);
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        const includeTarget = request.query.scope === "vs-target-branch";
        const diff = await workspaceDiff({
          workingDir,
          contextLines: request.query.context_lines,
          targetBranch: includeTarget ? workspace.targetBranch : null,
        });
        return { diff: diffArtifactToWire(diff) };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id/commits",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: CommitHistorySchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        const workspace = requireWorkspace(request.params.workspace_id);
        const row = getWorkspace(getOrm(), request.params.workspace_id);
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        // The fork point is merge-base(HEAD, target); the source git hash is the
        // fallback when there's no target / the merge-base can't be computed.
        const history = await listCommits({
          workingDir,
          sourceGitHash: row?.sourceGitHash ?? "",
          targetBranch: workspace.targetBranch,
        });
        return commitHistoryToWire(history);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id/commit-diff",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        querystring: z.object({ commit_hash: z.string() }),
        response: { 200: CommitDiffSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        requireWorkspace(request.params.workspace_id);
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        const result = await commitDiff(workingDir, request.query.commit_hash);
        return {
          diff: result.diff,
          commitHash: result.commit_hash,
          parentHash: result.parent_hash,
        };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/read-file",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: z.object({ filePath: z.string() }),
        response: { 200: ReadFileResponseSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        requireWorkspace(request.params.workspace_id);
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        const target = path.isAbsolute(request.body.filePath)
          ? request.body.filePath
          : path.join(workingDir, request.body.filePath);
        if (!existsSync(target) || !statSync(target).isFile()) {
          return reply.code(404).send({ detail: "File not found" });
        }
        return readFileContent(target);
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );

  typed.post(
    "/api/v1/workspaces/:workspace_id/read-file-at-ref",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        body: z.object({ path: z.string(), gitRef: z.string() }),
        response: { 200: ReadFileResponseSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        requireWorkspace(request.params.workspace_id);
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        const content = await readFileAtRef(
          workingDir,
          request.body.gitRef,
          request.body.path,
        );
        return { content, encoding: "utf-8" as const };
      } catch (error) {
        if (error instanceof WorkspaceError) {
          return handleError(error, reply);
        }
        return reply.code(404).send({ detail: "File not found at ref" });
      }
    },
  );

  typed.get(
    "/api/v1/workspaces/:workspace_id/files",
    {
      schema: {
        params: WorkspaceIdParamsSchema,
        response: { 200: WorkspaceFileListSchema, ...errorResponses },
      },
    },
    async (request, reply) => {
      try {
        requireWorkspace(request.params.workspace_id);
        const workingDir = getWorkspaceWorkingDirectory(
          request.params.workspace_id,
        );
        const listed = await runGit(
          ["ls-files", "--cached", "--others", "--exclude-standard"],
          workingDir,
        );
        const filePaths = listed.stdout
          .split("\n")
          .map((line) => line.trim())
          .filter((line) => line !== "");
        const directories = new Set<string>();
        for (const filePath of filePaths) {
          const parts = filePath.split("/");
          for (let i = 1; i < parts.length; i++) {
            directories.add(parts.slice(0, i).join("/"));
          }
        }
        const files = [
          ...[...directories]
            .sort()
            .map((dir) => ({ path: dir, type: "directory" as const })),
          ...filePaths.map((filePath) => ({
            path: filePath,
            type: "file" as const,
          })),
        ];
        return { files };
      } catch (error) {
        return handleError(error, reply);
      }
    },
  );
}
