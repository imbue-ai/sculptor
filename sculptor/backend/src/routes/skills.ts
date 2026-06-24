import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getOrm } from "~/db/orm";
import { getRepo } from "~/db/repositories";
import { localPathFromRepo } from "~/services/project";
import { getWorkspaceWorkingDirectory } from "~/services/workspace";

// GET /api/v1/skills (web/skills.py). Discovers SKILL.md skills from the repo's
// .claude/skills and the user's ~/.claude/skills, deduped by name and sorted.
// NOTE: plugin-namespaced skills and command (.md) sources are a follow-up; the
// skills panel's primary source is the repo/home skill directories.

interface SkillInfoWire {
  name: string;
  description: string;
  source: string;
  filePath: string;
}

function parseFrontmatter(content: string): {
  name?: string;
  description?: string;
} {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content);
  if (match === null) {
    return {};
  }
  const out: { name?: string; description?: string } = {};
  for (const line of match[1]!.split(/\r?\n/)) {
    const kv = /^(name|description):\s*(.*)$/.exec(line.trim());
    if (kv !== null) {
      out[kv[1] as "name" | "description"] = kv[2]!
        .replace(/^["']|["']$/g, "")
        .trim();
    }
  }
  return out;
}

function scanSkillsDir(
  dir: string,
  source: string,
  seen: Set<string>,
  out: SkillInfoWire[],
): void {
  if (!existsSync(dir)) {
    return;
  }
  for (const entry of readdirSync(dir)) {
    const skillFile = path.join(dir, entry, "SKILL.md");
    if (!existsSync(skillFile) || !statSync(skillFile).isFile()) {
      continue;
    }
    const { name, description } = parseFrontmatter(
      readFileSync(skillFile, "utf8"),
    );
    const skillName = name ?? entry;
    if (seen.has(skillName)) {
      continue;
    }
    seen.add(skillName);
    out.push({
      name: skillName,
      description: description ?? "",
      source,
      filePath: skillFile,
    });
  }
}

function resolveRepoRoot(
  workspaceId: string | undefined,
  projectId: string | undefined,
): string | null {
  if (workspaceId !== undefined) {
    try {
      return getWorkspaceWorkingDirectory(workspaceId);
    } catch {
      return null;
    }
  }
  if (projectId !== undefined) {
    const repo = getRepo(getOrm(), projectId);
    return repo === undefined ? null : localPathFromRepo(repo);
  }
  return null;
}

export async function registerSkillRoutes(app: FastifyInstance): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  typed.get(
    "/api/v1/skills",
    {
      schema: {
        querystring: z.object({
          workspaceId: z.string().optional(),
          projectId: z.string().optional(),
        }),
        response: {
          200: z.array(
            z.object({
              name: z.string(),
              description: z.string(),
              source: z.string(),
              filePath: z.string(),
            }),
          ),
          400: z.object({ detail: z.string() }),
        },
      },
    },
    async (request, reply) => {
      const { workspaceId, projectId } = request.query;
      if ((workspaceId === undefined) === (projectId === undefined)) {
        return reply
          .code(400)
          .send({
            detail: "Exactly one of workspaceId or projectId must be provided",
          });
      }
      const seen = new Set<string>();
      const out: SkillInfoWire[] = [];
      const repoRoot = resolveRepoRoot(workspaceId, projectId);
      if (repoRoot !== null) {
        scanSkillsDir(
          path.join(repoRoot, ".claude", "skills"),
          "custom",
          seen,
          out,
        );
      }
      scanSkillsDir(
        path.join(os.homedir(), ".claude", "skills"),
        "custom",
        seen,
        out,
      );
      out.sort((a, b) => a.name.localeCompare(b.name));
      return out;
    },
  );
}
