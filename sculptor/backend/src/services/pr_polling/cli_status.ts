import { execFile } from "node:child_process";

// CLI failure taxonomy + classifier (REQ-INT-003), ported from
// web/cli_status_utils.py. Each category must stay distinct so the UI can
// prompt for auth, show an access error, or wait out a throttle — collapsing
// them regresses the contract. `cli_missing` (the binary isn't on PATH) is a
// rewrite-side addition surfaced separately from the stderr-based categories.

export type CliErrorCategory =
  | "cli_missing"
  | "not_authenticated"
  | "no_access"
  | "network_error"
  | "rate_limited"
  | "transient";

export const NON_RETRYABLE_CLI_ERRORS: ReadonlySet<CliErrorCategory> =
  new Set<CliErrorCategory>([
    "cli_missing",
    "not_authenticated",
    "no_access",
    "network_error",
    "rate_limited",
  ]);

export class CliStatusError extends Error {
  constructor(
    readonly category: CliErrorCategory,
    readonly stderr: string,
  ) {
    super(stderr);
    this.name = "CliStatusError";
  }
}

// Classify a CLI error from its stderr (union of gh + glab keyword lists).
// Order matters: usage errors first (their help text lists field names like
// "author" that would trip the auth check), then rate limits, then auth.
export function classifyCliError(stderr: string): CliErrorCategory {
  const lower = stderr.toLowerCase();
  if (
    ["unknown json field", "unknown flag", "available fields:"].some((k) =>
      lower.includes(k),
    )
  ) {
    return "transient";
  }
  if (
    ["rate limit", "ratelimit", "secondary rate"].some((k) => lower.includes(k))
  ) {
    return "rate_limited";
  }
  if (
    /\bauth\b/.test(lower) ||
    [
      "authentic",
      "authoriz",
      "not logged into",
      "not logged",
      "log in",
      "token",
      "401",
    ].some((k) => lower.includes(k))
  ) {
    return "not_authenticated";
  }
  if (
    ["403", "forbidden", "access denied", "permission"].some((k) =>
      lower.includes(k),
    )
  ) {
    return "no_access";
  }
  if (
    ["could not resolve", "no such host", "dns"].some((k) => lower.includes(k))
  ) {
    return "network_error";
  }
  if (
    /(?:HTTP[/ ]|status[: ]*)5\d{2}\b/i.test(stderr) ||
    lower.includes("timeout") ||
    lower.includes("connection refused")
  ) {
    return "transient";
  }
  return "transient";
}

export interface CliResult {
  code: number;
  stdout: string;
  stderr: string;
}

// The injectable command runner — overridden in tests so no real gh/glab is
// spawned. The default shells out via execFile (no shell, argv array).
export type CliRunner = (
  cmd: readonly string[],
  cwd: string,
) => Promise<CliResult>;

const CLI_TIMEOUT_MS = 30_000;

export const defaultCliRunner: CliRunner = (cmd, cwd) =>
  new Promise<CliResult>((resolve, reject) => {
    execFile(
      cmd[0]!,
      cmd.slice(1),
      { cwd, timeout: CLI_TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout, stderr) => {
        if (
          error !== null &&
          (error as NodeJS.ErrnoException).code === "ENOENT"
        ) {
          reject(
            new CliStatusError(
              "cli_missing",
              `${cmd[0]} CLI not found in PATH`,
            ),
          );
          return;
        }
        const code =
          error !== null &&
          typeof (error as { code?: unknown }).code === "number"
            ? (error as { code: number }).code
            : 0;
        resolve({ code, stdout, stderr });
      },
    );
  });

// Run a CLI command, classifying a non-zero exit into the taxonomy. A missing
// binary surfaces as `cli_missing` (the runner rejects with that category).
export async function runCli(
  cmd: readonly string[],
  cwd: string,
  runner: CliRunner,
): Promise<CliResult> {
  const result = await runner(cmd, cwd);
  if (result.code !== 0) {
    throw new CliStatusError(classifyCliError(result.stderr), result.stderr);
  }
  return result;
}
