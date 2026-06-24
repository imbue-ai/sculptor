import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("runMigrations", () => {
  let dir: string;
  let db: DatabaseConnection;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-migrate-"));
    db = openDatabase(path.join(dir, "database.db"));
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("applies the migrations on a fresh DB and is a no-op at head", () => {
    runMigrations(db, MIGRATIONS_FOLDER);
    const tables = db
      .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
      .all()
      .map((row) => (row as { name: string }).name);
    for (const table of ["agent", "agent_message", "notification", "repo", "user_settings", "workspace"]) {
      expect(tables).toContain(table);
    }
    // Running again must not throw and must leave the schema intact.
    expect(() => runMigrations(db, MIGRATIONS_FOLDER)).not.toThrow();
  });

  it("fails loud when the store is stamped with a newer schema than the binary knows", () => {
    runMigrations(db, MIGRATIONS_FOLDER);
    db.exec("INSERT INTO __drizzle_migrations (hash, created_at) VALUES ('future-migration', 99999999999999)");
    expect(() => runMigrations(db, MIGRATIONS_FOLDER)).toThrow(/newer/);
  });
});
