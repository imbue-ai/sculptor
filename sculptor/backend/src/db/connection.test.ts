import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { transaction } from "~/db/transaction";

describe("openDatabase", () => {
  let dir: string;
  let db: DatabaseConnection;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-db-"));
    db = openDatabase(path.join(dir, "database.db"));
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("applies the durability PRAGMAs", () => {
    expect(db.pragma("journal_mode", { simple: true })).toBe("wal");
    expect(db.pragma("synchronous", { simple: true })).toBe(1);
    expect(db.pragma("busy_timeout", { simple: true })).toBe(15000);
    expect(db.pragma("foreign_keys", { simple: true })).toBe(1);
  });
});

describe("transaction", () => {
  let dir: string;
  let db: DatabaseConnection;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-db-"));
    db = openDatabase(path.join(dir, "database.db"));
    db.exec("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL)");
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("commits on success", () => {
    transaction(db, () => {
      db.prepare("INSERT INTO t (v) VALUES (?)").run("a");
      db.prepare("INSERT INTO t (v) VALUES (?)").run("b");
    });
    const count = db.prepare("SELECT COUNT(*) AS n FROM t").get() as { n: number };
    expect(count.n).toBe(2);
  });

  it("rolls back on a thrown error", () => {
    expect(() =>
      transaction(db, () => {
        db.prepare("INSERT INTO t (v) VALUES (?)").run("a");
        throw new Error("boom");
      }),
    ).toThrow("boom");
    const count = db.prepare("SELECT COUNT(*) AS n FROM t").get() as { n: number };
    expect(count.n).toBe(0);
  });
});
