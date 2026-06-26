import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

import { getPluginDirs, getPluginNamespace } from "~/config/plugins";
import { getOrm } from "~/db/orm";
import { getRepo } from "~/db/repositories";
import { localPathFromRepo } from "~/services/project";
import { getWorkspaceWorkingDirectory } from "~/services/workspace";

// GET /api/v1/skills (web/skills.py). Discovers SKILL.md skills from the bundled
// plugins (namespaced as `<plugin>:<skill>`, source "plugin"), the repo's
// .claude/skills, and the user's ~/.claude/skills, deduped by (namespaced) name
// and sorted. Command (.md) sources remain a follow-up.

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
  namespace: string | null,
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
    const baseName = name ?? entry;
    const skillName =
      namespace !== null ? `${namespace}:${baseName}` : baseName;
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
          workspace_id: z.string().optional(),
          project_id: z.string().optional(),
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
      const { workspace_id: workspaceId, project_id: projectId } =
        request.query;
      if ((workspaceId === undefined) === (projectId === undefined)) {
        return reply.code(400).send({
          detail: "Exactly one of workspaceId or projectId must be provided",
        });
      }
      const seen = new Set<string>();
      const out: SkillInfoWire[] = [];
      // Plugins first (namespaced, source "plugin"), then repo, then home —
      // first-name-wins on the namespaced name (skills.py discover_skills order).
      for (const pluginDir of getPluginDirs()) {
        scanSkillsDir(
          path.join(pluginDir, "skills"),
          "plugin",
          getPluginNamespace(pluginDir),
          seen,
          out,
        );
      }
      const repoRoot = resolveRepoRoot(workspaceId, projectId);
      if (repoRoot !== null) {
        scanSkillsDir(
          path.join(repoRoot, ".claude", "skills"),
          "custom",
          null,
          seen,
          out,
        );
      }
      scanSkillsDir(
        path.join(os.homedir(), ".claude", "skills"),
        "custom",
        null,
        seen,
        out,
      );
      out.sort((a, b) => a.name.localeCompare(b.name));
      return out;
    },
  );
}
