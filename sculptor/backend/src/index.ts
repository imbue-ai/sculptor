import type { FastifyInstance } from "fastify";

import { buildApp } from "~/app";
import { ensureSculptorFolderReady } from "~/config/bootstrap";
import { resolveBindHost, resolvePort } from "~/config/port";
import { closeDatabase, getDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { setupLogging } from "~/logging/logger";
import { emitOpenApiToFile } from "~/openapi";

// The integration harness scrapes stdout for this exact string to decide the
// backend is ready (READY_MESSAGE_V1 in sculptor/sculptor/testing/server_utils.py).
const READY_MESSAGE = "Server is ready to accept requests!";

function findFlagValue(argv: readonly string[], flag: string): string | undefined {
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
      () => {
        closeDatabase();
        process.exit(0);
      },
      () => {
        closeDatabase();
        process.exit(1);
      },
    );
  };
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
}

export async function main(argv: readonly string[] = process.argv): Promise<void> {
  const emitPath = findFlagValue(argv, "--emit-openapi");
  if (emitPath !== undefined) {
    await emitOpenApiToFile(emitPath);
    return;
  }

  // Bootstrap the on-disk Sculptor folder before opening any resources, then
  // configure logging so all later startup logs are captured, then open the DB.
  ensureSculptorFolderReady();
  const logger = setupLogging();
  const db = getDatabase();
  runMigrations(db);

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
