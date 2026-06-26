import type { FastifyInstance } from "fastify";

import { buildApp } from "~/app";
import { redactingRequestLogSerializer } from "~/auth/guard";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { resolveBindHost, resolvePort } from "~/config/port";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { setupLogging } from "~/logging/logger";
import { emitOpenApiToFile } from "~/openapi";
import { getAgentRunner } from "~/runner/instance";
import { getCIBabysitterCoordinator } from "~/services/ci_babysitter/coordinator";
import { getProjectService } from "~/services/project";
import { getPrPollingService } from "~/services/pr_polling/service";
import { getRepoPollingManager } from "~/services/repo_polling/manager";
import { installBundledRegistrations } from "~/services/terminal_agent_registry/bundled";
import { shutdownTelemetry } from "~/telemetry/posthog";

// The integration harness scrapes stdout for this exact string to decide the
// backend is ready (READY_MESSAGE_V1 in sculptor/sculptor/testing/server_utils.py).
const READY_MESSAGE = "Server is ready to accept requests!";

function findFlagValue(
  argv: readonly string[],
  flag: string,
): string | undefined {
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === undefined) {
      continue;
    }
    if (arg.startsWith(`${flag}=`)) {
      return arg.slice(flag.length + 1);
    }
    if (arg === flag && i + 1 < argv.length) {
      return argv[i + 1];
    }
  }
  return undefined;
}

function installShutdownHandlers(app: FastifyInstance): void {
  // Close the server cleanly on SIGTERM/SIGINT. The test harness sends SIGTERM
  // and escalates to SIGKILL if the process does not exit, so a hung close is
  // still bounded.
  const shutdown = (): void => {
    void app.close().then(
      async () => {
        await shutdownTelemetry();
        closeDatabase();
        process.exit(0);
      },
      async () => {
        await shutdownTelemetry();
        closeDatabase();
        process.exit(1);
      },
    );
  };
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
}

// Only --port/--host/--emit-openapi are read; any other flags are ignored. The
// Electron launcher (Task 9.2) passes the legacy --no-open-browser /
// --packaged-entrypoint flags — the headless backend never opens a browser, so
// they are accepted no-ops, keeping the launch command stable across the cutover.
export async function main(
  argv: readonly string[] = process.argv,
): Promise<void> {
  const emitPath = findFlagValue(argv, "--emit-openapi");
  if (emitPath !== undefined) {
    await emitOpenApiToFile(emitPath);
    return;
  }

  // Bootstrap the on-disk Sculptor folder before opening any resources, then
  // configure logging so all later startup logs are captured, then open the DB.
  ensureSculptorFolderReady();
  const logger = setupLogging();
  // Redact the session token from Fastify's auto-logged request URLs (it can
  // ride in a WebSocket query param). Fastify merges a logger instance's
  // serializers over its defaults, so this overrides the built-in `req` one.
  (logger as unknown as { serializers?: Record<string, unknown> }).serializers = {
    req: redactingRequestLogSerializer,
  };
  const db = getDatabase();
  runMigrations(db);

  // One-time install of the bundled Claude Code terminal-agent registration
  // (web/app.py install_bundled_registrations) so it appears in the agent-type
  // menu out of the box. Non-fatal.
  installBundledRegistrations();

  // Register the initial project path when one is passed as a positional arg
  // (the harness + the `sculptor <path>` invocation open a repo to start with),
  // idempotently — an already-added or invalid path is a non-fatal no-op. This
  // is what lets onboarding skip the add-repo step when a project already exists.
  const initialProjectPath = argv.slice(2).find((arg) => !arg.startsWith("--"));
  if (initialProjectPath !== undefined) {
    try {
      await getProjectService().initializeProject(initialProjectPath);
    } catch (error) {
      logger.info(
        `Initial project not registered (${initialProjectPath}): ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // Re-supervise every non-terminal agent (crash-recovery / cutover resume,
  // RW-DATA-6). The shared runner is wired with the harness registry resolver
  // (Task 5.6) + per-agent environment (Task 6.7).
  await getAgentRunner().resuperviseOnStartup();

  // Start PR/CI status polling (Task 7.1) — bounded pool + global spacing,
  // gated by pr_polling_enabled. Stopped on shutdown.
  getPrPollingService().start();

  // Start repo polling (Task 7.2) — 3 s branch + remote-branch refresh per open
  // workspace, stopping a workspace whose checkout is torn down.
  getRepoPollingManager().start();

  // Start the CI babysitter (Task 7.3) — off by default, consumes pr_status.
  getCIBabysitterCoordinator().start();

  const port = resolvePort(argv);
  const host = resolveBindHost();
  const app = buildApp({ loggerInstance: logger });
  installShutdownHandlers(app);

  await app.listen({ port, host });

  // The printed URL is scraped by the Electron launcher's parseUrlFromStdout
  // (matches https?://[^\s]+:\d+); the ready line is scraped by the test harness.
  // eslint-disable-next-line no-console
  console.log(`Backend running at http://${host}:${port}`);
  // eslint-disable-next-line no-console
  console.log(READY_MESSAGE);
}

// This module is the server entrypoint (the esbuild bundle target and the tsx
// dev target). It is never imported by tests — those import buildApp /
// generateOpenApiDocument directly — so running main() here has no test
// side effects.
main().catch((error: unknown) => {
  // eslint-disable-next-line no-console
  console.error(error);
  process.exit(1);
});
