// Builds the `pi --mode rpc` launch command + API-key env injection, ported from
// `pi_agent/agent_wrapper.py:start`. Unlike Claude, pi is NOT wrapped in
// `bash -c`; it is executed directly as a long-lived RPC subprocess. Pins pi
// 0.78.0.

import { PiBinaryNotFoundError } from "~/harness/errors";

// Resolve the host `pi` binary, raising the specific, surfaced
// PiBinaryNotFoundError when it is absent.
export function resolvePiBinary(resolver: () => string | undefined): string {
  const binaryPath = resolver();
  if (binaryPath === undefined) {
    throw new PiBinaryNotFoundError();
  }
  return binaryPath;
}

// The default API-key env vars looked up at spawn (config.pi.api_key_env_var_names).
export const DEFAULT_PI_API_KEY_ENV_VAR_NAMES: readonly string[] = [
  "ANTHROPIC_API_KEY",
];

// Per-task pi state, mirroring agent_wrapper's PI_SESSION_DIR_NAME / state file.
export const PI_SESSION_DIR_NAME = "pi_session";
export const PI_SESSION_ID_STATE_FILE = "pi_session_id";

export interface PiCommandOptions {
  binaryPath: string;
  sessionDir: string;
  sessionId: string;
  systemPrompt: string;
  // Absolute paths to the pinned extensions (`-e <path>` per extension).
  extensionPaths?: readonly string[];
  // Workspace skill source directories (`--skill <dir>` per directory).
  skillDirs?: readonly string[];
}

// Returns the full argv. `--no-extensions` disables pi's own extension
// discovery while the explicit `-e <path>` still loads the pinned set (the
// immutability guarantee).
export function getPiCommand(options: PiCommandOptions): string[] {
  const extensionArgs = (options.extensionPaths ?? []).flatMap((p) => [
    "-e",
    p,
  ]);
  const skillArgs = (options.skillDirs ?? []).flatMap((d) => ["--skill", d]);
  return [
    options.binaryPath,
    "--mode",
    "rpc",
    "--session-dir",
    options.sessionDir,
    "--session-id",
    options.sessionId,
    "--no-extensions",
    ...extensionArgs,
    "--append-system-prompt",
    options.systemPrompt,
    ...skillArgs,
  ];
}

// Collect the configured API-key env vars present in the process environment,
// to inject into the pi child's env. Values live only in the child's
// environment and are never persisted. Mirrors
// `_collect_api_key_secrets`.
export function collectApiKeySecrets(
  apiKeyEnvVarNames: readonly string[] = DEFAULT_PI_API_KEY_ENV_VAR_NAMES,
  env: NodeJS.ProcessEnv = process.env,
): Record<string, string> {
  const collected: Record<string, string> = {};
  for (const name of apiKeyEnvVarNames) {
    const value = env[name];
    if (value) {
      collected[name] = value;
    }
  }
  return collected;
}
