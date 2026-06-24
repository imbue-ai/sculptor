import { createOrm } from "~/db/orm";
import { openDatabase } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import {
  agent,
  agentMessage,
  notification,
  repo,
  userSettings,
  workspace,
} from "~/db/schema";
import { assertMigratable, readOldStore } from "~/migrate/read_old_db";
import { transformStore } from "~/migrate/transform";

// The core migration step: read the OLD store, transform, and write a FRESH
// new-schema database at targetDbPath. Pure with respect to the source (opened
// read-only) — the CLI (index.ts) owns the backup + swap of the live file. The
// inserts run in one transaction in FK-safe order (repos before workspaces
// before agents before messages/notifications).

export interface MigrationSummary {
  userSettings: number;
  repos: number;
  workspaces: number;
  agents: number;
  agentMessages: number;
  notifications: number;
}

export interface MigrateOptions {
  sourceDbPath: string;
  targetDbPath: string;
  migrationsFolder?: string;
}

export function migrateDatabase(options: MigrateOptions): MigrationSummary {
  assertMigratable(options.sourceDbPath);
  const newStore = transformStore(readOldStore(options.sourceDbPath));

  const db = openDatabase(options.targetDbPath);
  try {
    runMigrations(db, options.migrationsFolder);
    const orm = createOrm(db);
    orm.transaction((tx) => {
      if (newStore.userSettings.length > 0) {
        tx.insert(userSettings).values(newStore.userSettings).run();
      }
      if (newStore.repos.length > 0) {
        tx.insert(repo).values(newStore.repos).run();
      }
      if (newStore.workspaces.length > 0) {
        tx.insert(workspace).values(newStore.workspaces).run();
      }
      if (newStore.agents.length > 0) {
        tx.insert(agent).values(newStore.agents).run();
      }
      if (newStore.agentMessages.length > 0) {
        tx.insert(agentMessage).values(newStore.agentMessages).run();
      }
      if (newStore.notifications.length > 0) {
        tx.insert(notification).values(newStore.notifications).run();
      }
    });
  } finally {
    db.close();
  }

  return {
    userSettings: newStore.userSettings.length,
    repos: newStore.repos.length,
    workspaces: newStore.workspaces.length,
    agents: newStore.agents.length,
    agentMessages: newStore.agentMessages.length,
    notifications: newStore.notifications.length,
  };
}
