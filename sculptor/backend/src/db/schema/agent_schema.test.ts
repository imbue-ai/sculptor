import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { eq } from "drizzle-orm";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import * as schema from "~/db/schema";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("agent/agent_message/notification schema", () => {
  let dir: string;
  let db: DatabaseConnection;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-agent-schema-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("round-trips an agent including JSON columns and the run_state enum", () => {
    const orm = drizzle(db, { schema });
    orm.insert(schema.repo).values({ objectId: "repo_1", name: "r" }).run();
    orm
      .insert(schema.agent)
      .values({
        objectId: "tsk_1",
        projectId: "repo_1",
        agentConfig: { object_type: "ClaudeAgentConfig", model: "claude" },
        runState: "RUNNING",
        startingGitHash: "abc123",
        availableModels: [{ id: "m1" }],
        terminalShellPid: 4242,
      })
      .run();

    const row = orm.select().from(schema.agent).where(eq(schema.agent.objectId, "tsk_1")).get();
    expect(row?.runState).toBe("RUNNING");
    expect(row?.agentConfig).toEqual({ object_type: "ClaudeAgentConfig", model: "claude" });
    expect(row?.availableModels).toEqual([{ id: "m1" }]);
    expect(row?.terminalShellPid).toBe(4242);
    expect(row?.isDeleted).toBe(false);

    // Defaults applied for an agent created with the minimum fields.
    orm.insert(schema.agent).values({ objectId: "tsk_2", projectId: "repo_1", agentConfig: {} }).run();
    const minimal = orm.select().from(schema.agent).where(eq(schema.agent.objectId, "tsk_2")).get();
    expect(minimal?.runState).toBe("QUEUED");
    expect(minimal?.availableModels).toEqual([]);
  });

  it("appends agent_message rows and stores a notification with default importance", () => {
    const orm = drizzle(db, { schema });
    orm.insert(schema.repo).values({ objectId: "repo_1", name: "r" }).run();
    orm.insert(schema.agent).values({ objectId: "tsk_1", projectId: "repo_1", agentConfig: {} }).run();

    orm
      .insert(schema.agentMessage)
      .values({ objectId: "agtm_1", agentId: "tsk_1", message: { message_id: "agtm_1" }, source: "USER", isPartial: false })
      .run();
    const message = orm.select().from(schema.agentMessage).where(eq(schema.agentMessage.objectId, "agtm_1")).get();
    expect(message?.source).toBe("USER");
    expect(message?.isPartial).toBe(false);
    expect(message?.message).toEqual({ message_id: "agtm_1" });

    orm.insert(schema.notification).values({ objectId: "ntf_1", message: "hello", agentId: "tsk_1" }).run();
    const note = orm.select().from(schema.notification).where(eq(schema.notification.objectId, "ntf_1")).get();
    expect(note?.importance).toBe("ACTIVE");
  });
});
