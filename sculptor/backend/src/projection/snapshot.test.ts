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
  ensureUserSettings,
  softDeleteWorkspace,
} from "~/db/repositories";
import { ProjectionCache } from "~/projection/cache";
import { buildSnapshot } from "~/projection/snapshot";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");

function userTurn(text: string, suffix: string): Record<string, unknown>[] {
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

describe("buildSnapshot", () => {
  let dir: string;
  let db: DatabaseConnection;
  let orm: Orm;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-snapshot-"));
    db = openDatabase(path.join(dir, "database.db"));
    runMigrations(db, MIGRATIONS_FOLDER);
    orm = createOrm(db);
  });

  afterEach(() => {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  });

  it("yields a wire-correct full snapshot from current state + warm cache", () => {
    createRepo(orm, { objectId: "repo_1", name: "myrepo", userGitRepoUrl: "file:///tmp/r" });
    createWorkspace(orm, {
      objectId: "ws_1",
      projectId: "repo_1",
      description: "work",
      initializationStrategy: "WORKTREE",
    });
    createAgent(orm, {
      objectId: "tsk_1",
      projectId: "repo_1",
      workspaceId: "ws_1",
      agentConfig: { object_type: "ClaudeCodeSDKAgentConfig" },
    });
    for (const m of userTurn("hello", "1")) {
      appendAgentMessage(orm, "tsk_1", m);
    }
    ensureUserSettings(orm, "uset_1");
    createNotification(orm, { objectId: "ntf_1", message: "done", agentId: "tsk_1" });

    const cache = new ProjectionCache();
    const update = buildSnapshot(orm, { kind: "all" }, { cache });

    // Per-agent view + task_update.
    expect(Object.keys(update.task_views_by_task_id)).toEqual(["tsk_1"]);
    expect(update.task_views_by_task_id["tsk_1"]?.object_type).toBe("CodingAgentTaskView");
    expect(update.task_update_by_task_id["tsk_1"]?.task_id).toBe("tsk_1");
    expect(update.task_update_by_task_id["tsk_1"]?.chat_messages.length).toBeGreaterThan(0);

    // user_update carries projects / workspaces / notifications / user_settings.
    expect(update.user_update.projects.map((p) => p.object_id)).toEqual(["repo_1"]);
    expect(update.user_update.projects[0]?.name).toBe("myrepo");
    expect(update.user_update.workspaces.map((w) => w.object_id)).toEqual(["ws_1"]);
    expect(update.user_update.notifications.map((n) => n.object_id)).toEqual(["ntf_1"]);
    expect(update.user_update.notifications[0]?.task_id).toBe("tsk_1");
    expect(update.user_update.user_settings?.object_id).toBe("uset_1");

    // dependencies_status is present on the ScopeAll snapshot (null until the
    // service supplies it).
    expect(update).toHaveProperty("dependencies_status");
  });

  it("populates dependencies_status when supplied (ScopeAll)", () => {
    createRepo(orm, { objectId: "repo_1", name: "r" });
    const cache = new ProjectionCache();
    const deps = {
      git: emptyDep(),
      claude: emptyDep(),
      pi: emptyDep(),
    };
    const update = buildSnapshot(orm, { kind: "all" }, { cache, dependenciesStatus: deps });
    expect(update.dependencies_status).toEqual(deps);
  });

  it("ScopeAll snapshot omits soft-deleted repos and their workspaces", () => {
    createRepo(orm, { objectId: "repo_1", name: "r" });
    createWorkspace(orm, {
      objectId: "ws_1",
      projectId: "repo_1",
      description: "d",
      initializationStrategy: "WORKTREE",
    });
    softDeleteWorkspace(orm, "ws_1");
    const cache = new ProjectionCache();
    const update = buildSnapshot(orm, { kind: "all" }, { cache });
    // Deleted workspace is not listed under the project's workspaces.
    expect(update.user_update.workspaces).toEqual([]);
  });

  it("non-ScopeAll snapshot drops user_update / dependencies_status", () => {
    createRepo(orm, { objectId: "repo_1", name: "r" });
    const cache = new ProjectionCache();
    const update = buildSnapshot(orm, { kind: "workspace" }, { cache, dependenciesStatus: { git: emptyDep(), claude: emptyDep(), pi: emptyDep() } });
    expect(update.user_update.projects).toEqual([]);
    expect(update.user_update.notifications).toEqual([]);
    expect(update.dependencies_status).toBeNull();
  });
});

function emptyDep() {
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
