import { existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import path from "node:path";

import pino, { type Logger } from "pino";

import { logsDir } from "~/config/sculptor_folder";

// Process-wide structured logger, mirroring sculptor/sculptor/utils/logs.py:
// JSONL to internal/logs/server/logs.jsonl plus stderr, at a configurable
// level. The on-disk path + JSONL format are the contract the diagnostics
// upload bundles; the rotation policy is a comparable (not
// byte-identical) approximation of the Python ~0.1 GB / 10-file policy.

const DEFAULT_LOG_LEVEL = "debug";
// ~0.1 GB, matching the Python rotation trigger.
const ROTATION_SIZE_BYTES = 100 * 1024 * 1024;
const RETENTION_COUNT = 10;

export function resolveLogLevel(env: NodeJS.ProcessEnv = process.env): string {
  const level = env.LOG_LEVEL;
  return level !== undefined && level !== "" ? level.toLowerCase() : DEFAULT_LOG_LEVEL;
}

export function serverLogFilePath(env: NodeJS.ProcessEnv = process.env): string {
  return path.join(logsDir(env), "server", "logs.jsonl");
}

// Rotate the active log file when it grows past the threshold, pruning archives
// beyond the retention count. Runs at startup so the active file stays at the
// canonical logs.jsonl path the diagnostics bundle expects.
function rotateIfNeeded(file: string): void {
  if (!existsSync(file) || statSync(file).size < ROTATION_SIZE_BYTES) {
    return;
  }
  renameSync(file, `${file}.${statSync(file).mtimeMs}`);
  const dir = path.dirname(file);
  const prefix = `${path.basename(file)}.`;
  const archives = readdirSync(dir)
    .filter((name) => name.startsWith(prefix))
    .map((name) => path.join(dir, name))
    .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  for (const stale of archives.slice(RETENTION_COUNT)) {
    rmSync(stale, { force: true });
  }
}

let rootLogger: Logger = pino({ level: resolveLogLevel() }, pino.destination(2));

export function getLogger(): Logger {
  return rootLogger;
}

// Configures the process-wide logger to write to stderr and the JSONL file
// sink. Call early in startup, after the folder bootstrap and before opening
// the DB / starting services, so their startup logs are captured.
export function setupLogging(env: NodeJS.ProcessEnv = process.env): Logger {
  const file = serverLogFilePath(env);
  mkdirSync(path.dirname(file), { recursive: true });
  rotateIfNeeded(file);
  const level = resolveLogLevel(env);
  rootLogger = pino(
    { level },
    pino.multistream([
      { stream: process.stderr, level },
      { stream: pino.destination({ dest: file, mkdir: true, append: true, sync: true }), level },
    ]),
  );
  return rootLogger;
}
