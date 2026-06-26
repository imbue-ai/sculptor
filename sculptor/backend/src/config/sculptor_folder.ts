import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

// On-disk Sculptor folder layout, mirroring sculptor/sculptor/utils/build.py.
// The override env var name MUST match Python's exactly, or the integration
// harness's per-test folder isolation breaks.
export const SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG = "SCULPTOR_FOLDER";
export const SCULPTOR_WORKSPACES_FOLDER_OVERRIDE_ENV_FLAG = "SCULPTOR_WORKSPACES_FOLDER";

// Walk up from `startDir` looking for a `.git` entry — the repo root. Mirrors
// Python's `_get_repo_root()` in utils/build.py. Returns null when none is found
// (e.g. a packaged build, whose bundle has no git checkout above it).
export function findRepoRoot(startDir: string): string | null {
  let current = path.resolve(startDir);
  for (;;) {
    if (existsSync(path.join(current, ".git"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

// Start the repo-root walk from this module's directory when available — the
// CJS bundle (`just start`/`just backend`) exposes `__dirname`. Under ESM
// (tsx: `just backend-ts`, and `--emit-openapi` via `generate-api`) `__dirname`
// is undefined, so fall back to the cwd; both sit inside the repo for any
// from-source run. `typeof` is safe on the undeclared identifier (no throw).
const REPO_ROOT_SEARCH_START = typeof __dirname !== "undefined" ? __dirname : process.cwd();

// Computed once: the repo root for a source checkout (built bundle, tsx dev, or
// Vitest), or null in a packaged install (no `.git` above the installed bundle).
const SOURCE_REPO_ROOT = findRepoRoot(REPO_ROOT_SEARCH_START);

// Pure folder resolver (DI-friendly for tests). Faithful to Python's
// get_sculptor_folder():
//   1. SCULPTOR_FOLDER env override → use it (the integration harness + the
//      packaged launcher set this).
//   2. Running from a source checkout → <repo>/.dev_sculptor, so each checkout
//      keeps its own data (matches electron/logger.ts for the unpackaged app,
//      and is what `just start`/`just backend` rely on — they don't set the
//      env var).
//   3. Otherwise → ~/.sculptor (packaged production default).
// NOTE: the packaged *dev*-build variant (~/.dev-sculptor) is still driven by
// the launcher setting SCULPTOR_FOLDER, not detected here — a packaged install
// has no repo root above the bundle, so it lands on (3) unless the launcher
// overrides.
export function resolveSculptorFolder(
  env: NodeJS.ProcessEnv,
  sourceRepoRoot: string | null,
  homeDir: string,
): string {
  const override = env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
  if (override !== undefined && override !== "") {
    return path.resolve(override);
  }
  if (sourceRepoRoot !== null) {
    return path.join(sourceRepoRoot, ".dev_sculptor");
  }
  return path.join(homeDir, ".sculptor");
}

export function getSculptorFolder(env: NodeJS.ProcessEnv = process.env): string {
  return resolveSculptorFolder(env, SOURCE_REPO_ROOT, os.homedir());
}

export function getInternalFolder(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getSculptorFolder(env), "internal");
}

export function getWorkspacesFolder(env: NodeJS.ProcessEnv = process.env): string {
  const override = env[SCULPTOR_WORKSPACES_FOLDER_OVERRIDE_ENV_FLAG];
  if (override !== undefined && override !== "") {
    return path.resolve(override);
  }
  return path.join(getSculptorFolder(env), "workspaces");
}

export function databasePath(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getInternalFolder(env), "database.db");
}

export function configPath(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getInternalFolder(env), "config.toml");
}

export function logsDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getInternalFolder(env), "logs");
}

export function uploadsDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getInternalFolder(env), "uploads");
}

export function artifactsDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getInternalFolder(env), "artifacts");
}

export function formatVersionPath(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(getSculptorFolder(env), ".format_version");
}
