import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm, type Orm } from "~/db/orm";
import {
  appendAgentMessage,
  createAgent,
  createNotification,
  createRepo,
  createWorkspace,
  deleteAgentMessage,
  ensureUserSettings,
  getAgentByIdOrPrefix,
  listActiveRepos,
  listAgentMessages,
  listAgentsByWorkspace,
  listWorkspacesByRepo,
  setAgentRunState,
  setWorkspaceDiffStatus,
  softDeleteAgent,
  softDeleteRepo,
} from "~/db/repositories";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

describe("repositories", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-repos-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
    orm = createOrm(db);
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("repo CRUD + soft-delete filtering", () => {
    createRepo(orm, { objectId: "repo_1", name: "a" });
    createRepo(orm, { objectId: "repo_2", name: "b" });
    expect(listActiveRepos(orm).map((r) => r.objectId)).toEqual(["repo_1", "repo_2"]);
    softDeleteRepo(orm, "repo_1");
    expect(listActiveRepos(orm).map((r) => r.objectId)).toEqual(["repo_2"]);
  });

  it("workspace listByRepo + diff-status update", () => {
    createRepo(orm, { objectId: "repo_1", name: "a" });
    createWorkspace(orm, { objectId: "ws_1", projectId: "repo_1", description: "d", initializationStrategy: "WORKTREE" });
    expect(listWorkspacesByRepo(orm, "repo_1").map((w) => w.objectId)).toEqual(["ws_1"]);
    setWorkspaceDiffStatus(orm, "ws_1", "READY");
    const ws = listWorkspacesByRepo(orm, "repo_1")[0];
    expect(ws?.diffStatus).toBe("READY");
    expect(ws?.diffUpdatedAt).not.toBeNull();
  });

  it("agent run-state, soft-delete filter, and prefix lookup", () => {
    createRepo(orm, { objectId: "repo_1", name: "a" });
    createWorkspace(orm, { objectId: "ws_1", projectId: "repo_1", description: "d", initializationStrategy: "WORKTREE" });
    createAgent(orm, { objectId: "tsk_abc123", projectId: "repo_1", workspaceId: "ws_1", agentConfig: {} });
    createAgent(orm, { objectId: "tsk_def456", projectId: "repo_1", workspaceId: "ws_1", agentConfig: {} });

    setAgentRunState(orm, "tsk_abc123", "RUNNING");
    expect(getAgentByIdOrPrefix(orm, "tsk_abc123")?.runState).toBe("RUNNING");
    // Unique short prefix resolves; ambiguous prefix does not.
    expect(getAgentByIdOrPrefix(orm, "tsk_abc")?.objectId).toBe("tsk_abc123");
    expect(getAgentByIdOrPrefix(orm, "tsk_")).toBeUndefined();

    expect(listAgentsByWorkspace(orm, "ws_1")).toHaveLength(2);
    softDeleteAgent(orm, "tsk_abc123");
    expect(listAgentsByWorkspace(orm, "ws_1").map((a) => a.objectId)).toEqual(["tsk_def456"]);
  });

  it("agent_messages append invariants, partial-exclusion, pagination, delete", () => {
    createRepo(orm, { objectId: "repo_1", name: "a" });
    createAgent(orm, { objectId: "tsk_1", projectId: "repo_1", agentConfig: {} });

    appendAgentMessage(orm, "tsk_1", { message_id: "m1", source: "USER", object_type: "ChatInputUserMessage" });
    appendAgentMessage(orm, "tsk_1", {
      message_id: "m2",
      source: "AGENT",
      object_type: "PartialResponseBlockAgentMessage",
    });
    appendAgentMessage(orm, "tsk_1", { message_id: "m3", source: "AGENT", object_type: "ResponseBlockAgentMessage" });

    // Partials excluded by default.
    expect(listAgentMessages(orm, "tsk_1").map((m) => m.objectId)).toEqual(["m1", "m3"]);
    // Included when asked, with is_partial correctly derived.
    const all = listAgentMessages(orm, "tsk_1", { includePartial: true });
    expect(all.map((m) => m.objectId)).toEqual(["m1", "m2", "m3"]);
    expect(all.find((m) => m.objectId === "m2")?.isPartial).toBe(true);
    // Pagination.
    expect(listAgentMessages(orm, "tsk_1", { includePartial: true, limit: 1, offset: 1 }).map((m) => m.objectId)).toEqual(
      ["m2"],
    );

    // Invariant: an unknown source is rejected.
    expect(() =>
      appendAgentMessage(orm, "tsk_1", { message_id: "m4", source: "BOGUS", object_type: "X" }),
    ).toThrow();
    // Invariant: a missing message_id is rejected.
    expect(() => appendAgentMessage(orm, "tsk_1", { source: "USER", object_type: "X" })).toThrow();

    deleteAgentMessage(orm, "m1");
    expect(listAgentMessages(orm, "tsk_1").map((m) => m.objectId)).toEqual(["m3"]);
  });

  it("notification + user_settings", () => {
    createRepo(orm, { objectId: "repo_1", name: "a" });
    const note = createNotification(orm, { objectId: "ntf_1", message: "hi", projectId: "repo_1" });
    expect(note.importance).toBe("ACTIVE");

    const first = ensureUserSettings(orm, "us_1");
    const second = ensureUserSettings(orm, "us_1");
    expect(second.objectId).toBe(first.objectId);
  });
});
