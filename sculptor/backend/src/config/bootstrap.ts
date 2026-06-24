import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { formatVersionPath, getSculptorFolder } from "~/config/sculptor_folder";

// Mirrors sculptor/sculptor/utils/migration.py.
export const FORMAT_VERSION = "1";

// Ensures the Sculptor data folder has the expected structure and version
// marker. Idempotent: returns early if the marker is already present, so an
// existing populated folder is never clobbered. Bootstraps a fresh or
// unversioned folder otherwise (REQ-DATA-022). Does NOT create database.db —
// Phase 2 owns DB open/PRAGMA.
export function ensureSculptorFolderReady(env: NodeJS.ProcessEnv = process.env): void {
  const root = getSculptorFolder(env);
  const marker = formatVersionPath(env);
  if (existsSync(marker)) {
    return;
  }
  mkdirSync(path.join(root, "internal"), { recursive: true });
  mkdirSync(path.join(root, "workspaces"), { recursive: true });
  writeFileSync(marker, `${FORMAT_VERSION}\n`);
}
