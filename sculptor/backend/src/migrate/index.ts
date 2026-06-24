import { copyFileSync, existsSync, renameSync, rmSync } from "node:fs";

import { databasePath } from "~/config/sculptor_folder";
import { migrateDatabase, type MigrationSummary } from "~/migrate/run";

// Standalone one-time migration CLI (run once at upgrade). It NEVER mutates the
// old DB in place: the old file is backed up + retained (trivial rollback), the
// new file is written separately and swapped in. The on-disk layout (workspaces,
// uploads, artifacts, session files, config.toml) is untouched (RW-DATA-5) — only
// the DB is rewritten. config.toml is the source of truth for user
// email/consent/defaults, so preserving it carries those across (RW-DATA-4).

const BACKUP_SUFFIX = ".pre-ts-migration.bak";
const TEMP_SUFFIX = ".migrated.tmp";
const WAL_SUFFIXES = ["-wal", "-shm"];

function removeWithSidecars(path: string): void {
  rmSync(path, { force: true });
  for (const suffix of WAL_SUFFIXES) {
    rmSync(path + suffix, { force: true });
  }
}

export function runMigrationCli(
  dbPath: string = databasePath(),
): MigrationSummary {
  if (!existsSync(dbPath)) {
    throw new Error(`No database found at ${dbPath} — nothing to migrate.`);
  }
  const backupPath = dbPath + BACKUP_SUFFIX;
  const tempPath = dbPath + TEMP_SUFFIX;
  if (existsSync(backupPath)) {
    throw new Error(
      `A backup already exists at ${backupPath} — migration appears to have already run. Remove it to re-run.`,
    );
  }

  // Write the fresh DB to a temp file first (the source is opened read-only).
  removeWithSidecars(tempPath);
  const summary = migrateDatabase({
    sourceDbPath: dbPath,
    targetDbPath: tempPath,
  });

  // Retain the old DB as a backup, then swap the new file into place.
  copyFileSync(dbPath, backupPath);
  removeWithSidecars(dbPath);
  renameSync(tempPath, dbPath);
  // The temp WAL/shm (if any) belong to the now-renamed new DB; leave them.

  return summary;
}

// `node migrate.js` entry. Prints a clear summary; exits non-zero on failure so
// the upgrade flow can detect a bad migration.
function main(): void {
  try {
    const summary = runMigrationCli();
    // eslint-disable-next-line no-console
    console.log(
      `Migration complete. Migrated: ${summary.repos} repos, ${summary.workspaces} workspaces, ` +
        `${summary.agents} agents, ${summary.agentMessages} messages, ${summary.notifications} notifications, ` +
        `${summary.userSettings} user-settings. Old DB backed up alongside the database file.`,
    );
  } catch (error) {
    // eslint-disable-next-line no-console
    console.error(
      `Migration failed: ${error instanceof Error ? error.message : String(error)}`,
    );
    process.exit(1);
  }
}

// Only run when invoked directly (the bundle entry), not when imported by tests.
if (
  process.argv[1]?.endsWith("migrate.js") === true ||
  process.argv[1]?.endsWith("migrate/index.ts") === true
) {
  main();
}
