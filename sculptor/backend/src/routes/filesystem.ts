import { existsSync, readdirSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";

// GET /api/v1/filesystem/list (web/app.py list_directories). Directory
// autocomplete for the path picker: lists subdirectories of the deepest
// existing ancestor, filtered by the typed leaf prefix (case-insensitive),
// hiding dotfiles unless the prefix itself starts with a dot.

function expandUser(input: string): string {
  if (input === "~" || input.startsWith("~/")) {
    return path.join(os.homedir(), input.slice(1));
  }
  return input;
}

export async function registerFilesystemRoutes(
  app: FastifyInstance,
): Promise<void> {
  const typed = app.withTypeProvider<ZodTypeProvider>();
  typed.get(
    "/api/v1/filesystem/list",
    {
      schema: {
        querystring: z.object({ path: z.string().default("~") }),
        response: {
          200: z.array(z.object({ name: z.string(), path: z.string() })),
        },
      },
    },
    async (request) => {
      const expanded = expandUser(request.query.path);
      let parent: string;
      let prefix: string;
      if (existsSync(expanded) && statSync(expanded).isDirectory()) {
        parent = expanded;
        prefix = "";
      } else {
        parent = path.dirname(expanded);
        prefix = path.basename(expanded).toLowerCase();
      }
      if (!existsSync(parent) || !statSync(parent).isDirectory()) {
        return [];
      }
      const results: { name: string; path: string }[] = [];
      let entries: string[];
      try {
        entries = readdirSync(parent);
      } catch {
        return [];
      }
      for (const name of entries) {
        if (prefix === "" && name.startsWith(".")) {
          continue;
        }
        if (!name.toLowerCase().startsWith(prefix)) {
          continue;
        }
        const full = path.join(parent, name);
        try {
          if (statSync(full).isDirectory()) {
            results.push({ name, path: full });
          }
        } catch {
          // Unreadable entry — skip.
        }
      }
      results.sort((a, b) => a.name.localeCompare(b.name));
      return results;
    },
  );
}
