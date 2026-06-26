import path from "node:path";

import { getSculptorFolder } from "~/config/sculptor_folder";
import { parseEnvFile, parseEnvFileNames } from "~/config/env_file";

// `.env` variable injection for agent/terminal subprocesses. Two sources: the
// global `~/.sculptor/.env` and the per-repo `<repo>/.sculptor/.env`.
// The contract pins the precedence: PER-REPO OVERRIDES GLOBAL. Values are
// secrets-adjacent — they are merged into a child's env at spawn time and never
// persisted; only the *names* are ever surfaced (env-var-names).

export function globalEnvPath(): string {
  return path.join(getSculptorFolder(), ".env");
}

export function repoEnvPath(repoLocalPath: string): string {
  return path.join(repoLocalPath, ".sculptor", ".env");
}

// Variables the agent's runtime owns — a `.env` must not override them (the
// agent sets PATH itself: real PATH + managed tool bins, run_agent/v1.py
// _build_agent_path). Dropping them here keeps the child's inherited value.
const RESERVED_ENV_VARS: ReadonlySet<string> = new Set(["PATH"]);

function withoutReserved(
  env: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(env)) {
    if (!RESERVED_ENV_VARS.has(name)) {
      out[name] = value;
    }
  }
  return out;
}

// The merged env for a repo: global first, then per-repo so the repo wins on a
// name collision. A repo with no local path gets the global set.
export function resolveEnv(
  repoLocalPath: string | null,
): Record<string, string> {
  const global = parseEnvFile(globalEnvPath());
  if (repoLocalPath === null) {
    return withoutReserved(global);
  }
  return withoutReserved({
    ...global,
    ...parseEnvFile(repoEnvPath(repoLocalPath)),
  });
}

export function globalEnvVarNames(): string[] {
  return parseEnvFileNames(globalEnvPath());
}

// Names only (never values) for the env-var-names surface.
export function projectEnvVarNames(repoLocalPath: string): string[] {
  return parseEnvFileNames(repoEnvPath(repoLocalPath));
}
