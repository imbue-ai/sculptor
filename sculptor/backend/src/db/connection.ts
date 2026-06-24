import Database from "better-sqlite3";

import { databasePath } from "~/config/sculptor_folder";

export type DatabaseConnection = Database.Database;

// ~15 s, matching the Python _SQLITE_BUSY_TIMEOUT_SEC (database/core.py). With
// the single-writer model the busy timeout only covers other processes (the
// migration tool, external readers).
const BUSY_TIMEOUT_MS = 15000;

// Opens a better-sqlite3 connection and applies the durability PRAGMAs
// (REQ-NFR-031): WAL journal mode (persistent, but re-asserted), NORMAL
// synchronous, the 15 s busy timeout, and foreign-key enforcement. WAL leaves
// -wal/-shm sidecar files next to the database file.
export function openDatabase(file: string): DatabaseConnection {
  const db = new Database(file);
  db.pragma("journal_mode = WAL");
  db.pragma("synchronous = NORMAL");
  db.pragma(`busy_timeout = ${BUSY_TIMEOUT_MS}`);
  db.pragma("foreign_keys = ON");
  return db;
}

let connection: DatabaseConnection | undefined;

// Process-wide single writer connection. Everything runs on one event loop, so
// DB access is naturally serialized through this one handle — there is only
// ever one writer (RW-SIMP: no lock-contention/retry logic).
export function getDatabase(): DatabaseConnection {
  if (connection === undefined) {
    connection = openDatabase(databasePath());
  }
  return connection;
}

export function closeDatabase(): void {
  if (connection !== undefined) {
    connection.close();
    connection = undefined;
  }
}
