import path from "node:path";

import { getSculptorFolder } from "~/config/sculptor_folder";
import { parseEnvFile, parseEnvFileNames } from "~/config/env_file";

// `.env` variable injection for agent/terminal subprocesses (REQ-INT-050). Two
// sources: the global `~/.sculptor/.env` and the per-repo `<repo>/.sculptor/.env`.
// The contract pins the precedence: PER-REPO OVERRIDES GLOBAL. Values are
// secrets-adjacent — they are merged into a child's env at spawn time and never
// persisted; only the *names* are ever surfaced (env-var-names, REQ-SEC-002).

export function globalEnvPath(): string {
  return path.join(getSculptorFolder(), ".env");
}

export function repoEnvPath(repoLocalPath: string): string {
  return path.join(repoLocalPath, ".sculptor", ".env");
}

// The merged env for a repo: global first, then per-repo so the repo wins on a
// name collision (REQ-INT-050). A repo with no local path gets the global set.
export function resolveEnv(
  repoLocalPath: string | null,
): Record<string, string> {
  const global = parseEnvFile(globalEnvPath());
  if (repoLocalPath === null) {
    return global;
  }
  return { ...global, ...parseEnvFile(repoEnvPath(repoLocalPath)) };
}

export function globalEnvVarNames(): string[] {
  return parseEnvFileNames(globalEnvPath());
}

// Names only (never values) for the env-var-names surface (REQ-SEC-002).
export function projectEnvVarNames(repoLocalPath: string): string[] {
  return parseEnvFileNames(repoEnvPath(repoLocalPath));
}
