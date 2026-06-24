import type { DatabaseConnection } from "~/db/connection";

// Runs fn inside a synchronous better-sqlite3 transaction: it commits when fn
// returns and rolls back if fn throws. Wrap any multi-statement
// read-modify-write in this to keep it atomic.
export function transaction<T>(db: DatabaseConnection, fn: () => T): T {
  return db.transaction(fn)();
}
