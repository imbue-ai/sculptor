import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { drizzle } from "drizzle-orm/better-sqlite3";
import { migrate } from "drizzle-orm/better-sqlite3/migrator";

import type { DatabaseConnection } from "~/db/connection";

// The drizzle-kit migration runner — the ONGOING schema runner that replaces
// Alembic. Distinct from the one-time data migration tool (migrate/). Applies
// the generated SQL forward-only at startup and fails loud if the store reports
// more applied migrations than this binary knows about (i.e. an older binary
// against a newer DB).

interface MigrationJournal {
  entries: { idx: number; tag: string }[];
}

export function defaultMigrationsFolder(
  env: NodeJS.ProcessEnv = process.env,
  cwd: string = process.cwd(),
): string {
  if (env.SCULPTOR_MIGRATIONS_DIR !== undefined && env.SCULPTOR_MIGRATIONS_DIR !== "") {
    return env.SCULPTOR_MIGRATIONS_DIR;
  }
  for (const candidate of [
    path.resolve(cwd, "drizzle"),
    path.resolve(cwd, "sculptor/backend/drizzle"),
    path.resolve(cwd, "../drizzle"),
  ]) {
    if (existsSync(path.join(candidate, "meta", "_journal.json"))) {
      return candidate;
    }
  }
  return path.resolve(cwd, "drizzle");
}

function knownMigrationCount(migrationsFolder: string): number {
  const journalPath = path.join(migrationsFolder, "meta", "_journal.json");
  if (!existsSync(journalPath)) {
    return 0;
  }
  const journal = JSON.parse(readFileSync(journalPath, "utf8")) as MigrationJournal;
  return journal.entries.length;
}

function appliedMigrationCount(db: DatabaseConnection): number {
  const exists = db
    .prepare("SELECT count(*) AS n FROM sqlite_master WHERE type='table' AND name='__drizzle_migrations'")
    .get() as { n: number };
  if (exists.n === 0) {
    return 0;
  }
  return (db.prepare("SELECT count(*) AS n FROM __drizzle_migrations").get() as { n: number }).n;
}

export function runMigrations(db: DatabaseConnection, migrationsFolder: string = defaultMigrationsFolder()): void {
  const known = knownMigrationCount(migrationsFolder);
  const applied = appliedMigrationCount(db);
  if (applied > known) {
    throw new Error(
      `Sculptor database is not compatible with this version of Sculptor: the schema is ` +
        `newer than this backend (${applied} migrations applied, ${known} known). ` +
        "Refusing to start to avoid corrupting a forward-migrated store.",
    );
  }
  migrate(drizzle(db), { migrationsFolder });
}
