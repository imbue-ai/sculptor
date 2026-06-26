import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { drizzle } from "drizzle-orm/better-sqlite3";
import { eq } from "drizzle-orm";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import * as schema from "~/db/schema";

// Applies the drizzle-kit-generated DDL. The formal migration runner lives in
// db/migrate.ts; this inline apply keeps the schema test self-contained.
function applyGeneratedSchema(db: DatabaseConnection): void {
  const dir = path.resolve(process.cwd(), "drizzle");
  for (const file of readdirSync(dir)
    .filter((name) => name.endsWith(".sql"))
    .sort()) {
    const sql = readFileSync(path.join(dir, file), "utf8");
    for (const statement of sql.split("--> statement-breakpoint")) {
      const trimmed = statement.trim();
      if (trimmed !== "") {
        db.exec(trimmed);
      }
    }
  }
}

describe("settings/repo/workspace schema", () => {
  let dir: string;
  let db: DatabaseConnection;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-schema-"));
    db = openDatabase(path.join(dir, "database.db"));
    applyGeneratedSchema(db);
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("creates the three tables", () => {
    const tables = db
      .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
      .all()
      .map((row) => (row as { name: string }).name);
    expect(tables).toContain("repo");
    expect(tables).toContain("user_settings");
    expect(tables).toContain("workspace");
  });

  it("round-trips a repo and workspace including enums", () => {
    const orm = drizzle(db, { schema });
    orm.insert(schema.repo).values({ objectId: "repo_1", name: "my-repo", userGitRepoUrl: "file:///tmp/r" }).run();
    orm
      .insert(schema.workspace)
      .values({
        objectId: "ws_1",
        projectId: "repo_1",
        description: "feature work",
        initializationStrategy: "WORKTREE",
        diffStatus: "READY",
        setupExitCode: 0,
        setupStartedAt: 1700000000.5,
      })
      .run();

    const repoRow = orm.select().from(schema.repo).where(eq(schema.repo.objectId, "repo_1")).get();
    expect(repoRow?.name).toBe("my-repo");
    expect(repoRow?.isPathAccessible).toBe(true);
    expect(repoRow?.isDeleted).toBe(false);

    const wsRow = orm.select().from(schema.workspace).where(eq(schema.workspace.objectId, "ws_1")).get();
    expect(wsRow?.initializationStrategy).toBe("WORKTREE");
    expect(wsRow?.diffStatus).toBe("READY");
    expect(wsRow?.isOpen).toBe(true);
    expect(wsRow?.setupStatus).toBe("pending");
    expect(wsRow?.setupStartedAt).toBe(1700000000.5);
  });

  it("enforces the workspace.project_id foreign key", () => {
    const orm = drizzle(db, { schema });
    expect(() =>
      orm
        .insert(schema.workspace)
        .values({
          objectId: "ws_bad",
          projectId: "repo_does_not_exist",
          description: "orphan",
          initializationStrategy: "CLONE",
        })
        .run(),
    ).toThrow();
  });
});
