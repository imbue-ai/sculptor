import Database from "better-sqlite3";

// Reads the OLD (Python-schema) Sculptor SQLite store read-only. Current state
// for the four dual-table entities lives in the `<entity>_latest` tables; the
// two logs (saved_agent_message, notification) are read directly. We return raw
// rows (JSON columns still strings) — transform.ts parses + maps them.

export type RawRow = Record<string, unknown>;

export interface OldStore {
  userSettings: RawRow[];
  projects: RawRow[];
  workspaces: RawRow[];
  tasks: RawRow[];
  messages: RawRow[];
  notifications: RawRow[];
}

// The old current-state tables this migration understands. Their absence (or the
// presence of new-schema markers) means the store isn't an old Python store.
const REQUIRED_OLD_TABLES = [
  "user_settings_latest",
  "project_latest",
  "workspace_latest",
  "task_latest",
  "saved_agent_message",
  "notification",
];

// New-schema tables — if present, the store was already migrated (or is newer).
const NEW_SCHEMA_MARKERS = ["agent", "repo", "__drizzle_migrations"];

function tableNames(db: Database.Database): Set<string> {
  const rows = db
    .prepare("SELECT name FROM sqlite_master WHERE type='table'")
    .all() as { name: string }[];
  return new Set(rows.map((row) => row.name));
}

// Forward-only guard (RW-DATA-8): fail loud rather than partially migrate a
// store that is already migrated, newer, or not an old Python store at all.
export function assertMigratable(sourceDbPath: string): void {
  const db = new Database(sourceDbPath, { readonly: true });
  try {
    const tables = tableNames(db);
    const newMarker = NEW_SCHEMA_MARKERS.find((name) => tables.has(name));
    if (newMarker !== undefined) {
      throw new Error(
        `Refusing to migrate: the store already has the new-schema table '${newMarker}'. It looks already-migrated or newer than this tool understands.`,
      );
    }
    const missing = REQUIRED_OLD_TABLES.filter((name) => !tables.has(name));
    if (missing.length > 0) {
      throw new Error(
        `Refusing to migrate: the store is missing expected old tables: ${missing.join(", ")}.`,
      );
    }
  } finally {
    db.close();
  }
}

export function readOldStore(sourceDbPath: string): OldStore {
  const db = new Database(sourceDbPath, { readonly: true });
  try {
    const all = (sql: string): RawRow[] => db.prepare(sql).all() as RawRow[];
    return {
      userSettings: all("SELECT * FROM user_settings_latest"),
      projects: all("SELECT * FROM project_latest"),
      workspaces: all("SELECT * FROM workspace_latest"),
      tasks: all("SELECT * FROM task_latest"),
      messages: all("SELECT * FROM saved_agent_message"),
      notifications: all("SELECT * FROM notification"),
    };
  } finally {
    db.close();
  }
}
