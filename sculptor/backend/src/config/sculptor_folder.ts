import os from "node:os";
import path from "node:path";

// On-disk Sculptor folder layout, mirroring sculptor/sculptor/utils/build.py.
// The override env var name MUST match Python's exactly, or the integration
// harness's per-test folder isolation breaks (REQ-DATA-001/002).
export const SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG = "SCULPTOR_FOLDER";
export const SCULPTOR_WORKSPACES_FOLDER_OVERRIDE_ENV_FLAG = "SCULPTOR_WORKSPACES_FOLDER";

export function getSculptorFolder(env: NodeJS.ProcessEnv = process.env): string {
  const override = env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
  if (override !== undefined && override !== "") {
    return path.resolve(override);
  }
  // Production default. The packaged/dev-build/source variants Python computes
  // are folded into the launcher/packaging (Task 9.1), which sets the env var.
  return path.join(os.homedir(), ".sculptor");
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
