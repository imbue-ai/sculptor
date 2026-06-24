import { drizzle, type BetterSQLite3Database } from "drizzle-orm/better-sqlite3";

import { getDatabase, type DatabaseConnection } from "~/db/connection";
import * as schema from "~/db/schema";

// The Drizzle ORM handle, typed with the full schema. Repositories take an Orm
// so they are testable against a temp DB; production callers pass getOrm().
export type Orm = BetterSQLite3Database<typeof schema>;

export function createOrm(db: DatabaseConnection): Orm {
  return drizzle(db, { schema });
}

let cached: Orm | undefined;
let cachedFor: DatabaseConnection | undefined;

export function getOrm(): Orm {
  const db = getDatabase();
  if (cached === undefined || cachedFor !== db) {
    cached = createOrm(db);
    cachedFor = db;
  }
  return cached;
}
