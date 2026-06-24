import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm, type Orm } from "~/db/orm";
import { appendAgentMessage, createAgent, createRepo, createWorkspace } from "~/db/repositories";
import { ProjectionCache } from "~/projection/cache";
import { foldMessages } from "~/projection/message_conversion";
import type { RawMessage } from "~/projection/message_log";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

// A minimal single-turn user->assistant->success log (mirrors the
// single_text_response fixture shape).
function turn(text: string, suffix: string): RawMessage[] {
  const reqId = `agm_user_${suffix}`;
  return [
    {
      object_type: "ChatInputUserMessage",
      message_id: reqId,
      source: "USER",
      approximate_creation_time: "2024-01-01T00:00:00Z",
      text,
      sent_via: null,
    },
    {
      object_type: "RequestStartedAgentMessage",
      message_id: `agm_start_${suffix}`,
      source: "AGENT",
      approximate_creation_time: "2024-01-01T00:00:01Z",
      request_id: reqId,
    },
    {
      object_type: "ResponseBlockAgentMessage",
      message_id: `agm_resp_${suffix}`,
      source: "AGENT",
      approximate_creation_time: "2024-01-01T00:00:02Z",
      role: "assistant",
      assistant_message_id: `assistant-${suffix}`,
      content: [{ object_type: "TextBlock", type: "text", text: `reply ${text}` }],
      parent_tool_use_id: null,
    },
    {
      object_type: "RequestSuccessAgentMessage",
      message_id: `agm_ok_${suffix}`,
      source: "AGENT",
      approximate_creation_time: "2024-01-01T00:00:03Z",
      request_id: reqId,
      error: null,
    },
  ];
}

describe("ProjectionCache", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-cache-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
    orm = createOrm(db);
    createRepo(orm, { objectId: "repo_1", name: "a" });
    createWorkspace(orm, {
      objectId: "ws_1",
      projectId: "repo_1",
      description: "d",
      initializationStrategy: "WORKTREE",
    });
    createAgent(orm, {
      objectId: "tsk_1",
      projectId: "repo_1",
      workspaceId: "ws_1",
      agentConfig: { object_type: "ClaudeCodeSDKAgentConfig" },
    });
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("lazy fill folds the persisted log on first need", () => {
    const messages = turn("hello", "1");
    for (const m of messages) {
      appendAgentMessage(orm, "tsk_1", m);
    }
    const cache = new ProjectionCache();
    const chat = cache.getChatMessages(orm, "tsk_1");
    expect(chat).toEqual(foldMessages(messages));
    expect(cache.getView(orm, "tsk_1")?.object_type).toBe("CodingAgentTaskView");
  });

  it("incremental applyMessage equals a full re-fold (consistency)", () => {
    const all = [...turn("first", "1"), ...turn("second", "2")];
    const cache = new ProjectionCache();
    // Apply each message incrementally (the warm-cache hot path).
    for (const m of all) {
      cache.applyMessage(orm, "tsk_1", m);
    }
    expect(cache.getChatMessages(orm, "tsk_1")).toEqual(foldMessages(all));
  });

  it("lazy fill of prior history then incremental apply equals full re-fold", () => {
    const first = turn("first", "1");
    for (const m of first) {
      appendAgentMessage(orm, "tsk_1", m);
    }
    const cache = new ProjectionCache();
    // Cold-fill from DB, then apply a new turn that is NOT yet in the DB.
    cache.ensure(orm, "tsk_1");
    const second = turn("second", "2");
    for (const m of second) {
      cache.applyMessage(orm, "tsk_1", m);
    }
    expect(cache.getChatMessages(orm, "tsk_1")).toEqual(foldMessages([...first, ...second]));
  });

  it("evicts agents and reports membership", () => {
    const cache = new ProjectionCache();
    cache.ensure(orm, "tsk_1");
    expect(cache.has("tsk_1")).toBe(true);
    cache.evict("tsk_1");
    expect(cache.has("tsk_1")).toBe(false);
  });

  it("bounds retained raw messages for the view recompute", () => {
    const cache = new ProjectionCache({ maxRawMessages: 4 });
    const all = [...turn("a", "1"), ...turn("b", "2"), ...turn("c", "3")];
    for (const m of all) {
      cache.applyMessage(orm, "tsk_1", m);
    }
    // The folded chat is unaffected by the raw-message bound (the fold keeps its
    // own state); both completed turns remain.
    expect(cache.getChatMessages(orm, "tsk_1").length).toBeGreaterThanOrEqual(2);
  });

  it("returns undefined for a missing agent", () => {
    const cache = new ProjectionCache();
    expect(cache.ensure(orm, "tsk_missing")).toBeUndefined();
    expect(cache.getView(orm, "tsk_missing")).toBeUndefined();
  });
});
