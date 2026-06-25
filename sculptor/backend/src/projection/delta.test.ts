import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "~/db/connection";
import { runMigrations } from "~/db/migrate";
import { createOrm, type Orm } from "~/db/orm";
import {
  createAgent,
  createNotification,
  createRepo,
  createWorkspace,
} from "~/db/repositories";
import { ProjectionCache } from "~/projection/cache";
import { DeltaBuilder, eventToDelta } from "~/projection/delta";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

const DEPS = {
  git: dep(),
  claude: dep(),
  pi: dep(),
};

function dep() {
  return {
    installed: true,
    path: "/usr/bin/x",
    version: "1.0",
    is_override: false,
    mode: null,
    version_range: null,
    is_version_in_range: null,
    managed_version: null,
    is_authenticated: null,
    install_progress: null,
    install_error: null,
  };
}

describe("eventToDelta / DeltaBuilder", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;
  let cache: ProjectionCache;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-delta-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
    orm = createOrm(db);
    cache = new ProjectionCache();
    createRepo(orm, { objectId: "repo_1", name: "r" });
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

  it("data_model_change -> user_update delta + finished_request_ids", () => {
    createNotification(orm, { objectId: "ntf_1", message: "hi", agentId: "tsk_1" });
    const delta = eventToDelta(
      {
        kind: "data_model_change",
        requestId: "req_abc",
        changedEntities: [
          { type: "notification", id: "ntf_1" },
          { type: "repo", id: "repo_1" },
          { type: "workspace", id: "ws_1" },
        ],
      },
      { orm, cache },
    );
    expect(delta).not.toBeNull();
    expect(delta?.user_update.notifications.map((n) => n.object_id)).toEqual(["ntf_1"]);
    expect(delta?.user_update.projects.map((p) => p.object_id)).toEqual(["repo_1"]);
    expect(delta?.user_update.workspaces.map((w) => w.object_id)).toEqual(["ws_1"]);
    expect(delta?.finished_request_ids).toEqual(["req_abc"]);
  });

  it("data_model_change with no request id emits no finished_request_ids", () => {
    const delta = eventToDelta(
      { kind: "data_model_change", changedEntities: [{ type: "repo", id: "repo_1" }] },
      { orm, cache },
    );
    expect(delta?.finished_request_ids).toEqual([]);
    expect(delta?.user_update.projects.map((p) => p.object_id)).toEqual(["repo_1"]);
  });

  it("dependencies_status is deduped: identical re-emit produces no change", () => {
    const builder = new DeltaBuilder({ orm, cache });
    const first = builder.eventToDelta({ kind: "dependencies_status", status: DEPS });
    expect(first?.dependencies_status).toEqual(DEPS);
    // Identical second emit -> no delta (streams.py L646-649).
    const second = builder.eventToDelta({ kind: "dependencies_status", status: DEPS });
    expect(second).toBeNull();
    // A changed status emits again.
    const changed = { ...DEPS, git: { ...DEPS.git, installed: false } };
    const third = builder.eventToDelta({ kind: "dependencies_status", status: changed });
    expect(third?.dependencies_status).toEqual(changed);
  });

  it("btw_update event -> btw_update delta", () => {
    const update = {
      workspace_id: "ws_1",
      agent_id: "tsk_1",
      request_id: "req_1",
      state: "done",
      answer: "42",
      error_message: null,
    };
    const delta = eventToDelta({ kind: "btw_update", update }, { orm, cache });
    expect(delta?.btw_update).toEqual(update);
  });

  it("agent_message event -> task_update + task_views via the warm cache", () => {
    const message = {
      object_type: "ChatInputUserMessage",
      message_id: "agm_user_1",
      source: "USER",
      approximate_creation_time: "2024-01-01T00:00:00Z",
      text: "hi",
      sent_via: null,
    };
    // The runner is the sole applier; the delta path only reads. Mirror that by
    // folding the message into the warm cache before emitting the delta.
    cache.applyMessage(orm, "tsk_1", message);
    const delta = eventToDelta({ kind: "agent_message", agentId: "tsk_1", message }, { orm, cache });
    const taskUpdate = delta?.task_update_by_task_id["tsk_1"];
    expect(taskUpdate?.task_id).toBe("tsk_1");
    expect(delta?.task_views_by_task_id["tsk_1"]?.object_type).toBe("CodingAgentTaskView");
    // A lone user message with no started request is queued (the fold defers it
    // until a request begins), so the cache reflects it as a queued chat message.
    expect(taskUpdate?.queued_chat_messages.length).toBeGreaterThan(0);
  });

  it("agent_status event -> task_views delta", () => {
    const delta = eventToDelta({ kind: "agent_status", agentId: "tsk_1" }, { orm, cache });
    expect(delta?.task_views_by_task_id["tsk_1"]?.object_type).toBe("CodingAgentTaskView");
  });

  it("workspace-keyed ui events map to their keyed dicts", () => {
    const open = { workspace_id: "ws_1", file_path: "a.ts", mode: "auto" };
    const openDelta = eventToDelta(
      { kind: "ui_open_file", workspaceId: "ws_1", action: open },
      { orm, cache },
    );
    expect(openDelta?.ui_open_file_by_workspace_id["ws_1"]).toEqual(open);

    const cmd = { workspace_id: "ws_1", seq: 1, kind: "navigate", url: "http://x" };
    const cmdDelta = eventToDelta(
      { kind: "ui_webview_command", workspaceId: "ws_1", command: cmd },
      { orm, cache },
    );
    expect(cmdDelta?.ui_webview_command_by_workspace_id["ws_1"]).toEqual(cmd);
  });
});
