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
import { type NewStore, transformStore } from "~/migrate/transform";

// The core migration step: read the OLD store, transform, and write a FRESH
// new-schema database at targetDbPath. Pure with respect to the source (opened
// read-only) — the CLI (index.ts) owns the backup + swap of the live file. The
// inserts run in one transaction in FK-safe order (repos before workspaces
// before agents before messages/notifications). Referential integrity is checked
// up front (before any DB is opened) so an orphaned reference fails loud with the
// offending row rather than aborting the transaction with a bare FK error.

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

// Verify every foreign-key reference in the transformed store points at a row we
// are about to insert. Without this, one orphaned reference in real historical
// data (e.g. an agent.workspace_id whose workspace is absent from the *_latest
// snapshot, or a notification/message task_id pointing at a missing agent) would
// abort the whole FK-enforced transaction with a bare "FOREIGN KEY constraint
// failed" and no clue which row. We fail loud here — before opening the target
// DB, so no partial write is possible — naming the offending entity, its id, and
// the missing parent id. Forward-only: we surface an actionable error rather than
// silently dropping orphans.
function assertReferentialIntegrity(store: NewStore): void {
  const repoIds = new Set(store.repos.map((row) => row.objectId));
  const workspaceIds = new Set(store.workspaces.map((row) => row.objectId));
  const agentIds = new Set(store.agents.map((row) => row.objectId));

  const fail = (
    entity: string,
    objectId: string,
    column: string,
    parentEntity: string,
    parentId: string,
  ): never => {
    throw new Error(
      `Migration: ${entity} '${objectId}' references ${parentEntity} '${parentId}' via ` +
        `${column}, but no such ${parentEntity} exists in the source store. Refusing to ` +
        "migrate to avoid a partial write — resolve or remove the orphaned row first.",
    );
  };

  for (const ws of store.workspaces) {
    if (!repoIds.has(ws.projectId)) {
      fail("workspace", ws.objectId, "project_id", "repo", ws.projectId);
    }
  }
  for (const ag of store.agents) {
    if (!repoIds.has(ag.projectId)) {
      fail("agent", ag.objectId, "project_id", "repo", ag.projectId);
    }
    if (ag.workspaceId != null && !workspaceIds.has(ag.workspaceId)) {
      fail("agent", ag.objectId, "workspace_id", "workspace", ag.workspaceId);
    }
  }
  for (const msg of store.agentMessages) {
    if (!agentIds.has(msg.agentId)) {
      fail("agent_message", msg.objectId, "agent_id", "agent", msg.agentId);
    }
  }
  for (const ntf of store.notifications) {
    if (ntf.agentId != null && !agentIds.has(ntf.agentId)) {
      fail("notification", ntf.objectId, "agent_id", "agent", ntf.agentId);
    }
    if (ntf.projectId != null && !repoIds.has(ntf.projectId)) {
      fail("notification", ntf.objectId, "project_id", "repo", ntf.projectId);
    }
  }
}

export function migrateDatabase(options: MigrateOptions): MigrationSummary {
  assertMigratable(options.sourceDbPath);
  const newStore = transformStore(readOldStore(options.sourceDbPath));
  assertReferentialIntegrity(newStore);

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
