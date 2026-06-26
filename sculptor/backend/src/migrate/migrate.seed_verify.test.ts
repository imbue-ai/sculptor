import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import Database from "better-sqlite3";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase } from "~/db/connection";
import { createOrm } from "~/db/orm";
import {
  getAgent,
  getAgentMessage,
  getNotification,
  getRepo,
  getUserSettings,
  getWorkspace,
} from "~/db/repositories";
import { migrateDatabase } from "~/migrate/run";

const MIGRATIONS_FOLDER = path.resolve(process.cwd(), "drizzle");
const AGENT_ID = "tsk_abc123"; // a tsk_ id — must survive verbatim (on-disk paths / --resume)

// Build a minimal-but-representative OLD (Python-schema) store: the four
// <entity>_latest current-state tables + the two single-table logs, with a
// non-terminal agent whose current_state carries a session id + model catalog.
function seedOldStore(dbPath: string): void {
  const db = new Database(dbPath);
  db.exec(`
    CREATE TABLE user_settings_latest (object_id TEXT, created_at TEXT, user_reference TEXT);
    CREATE TABLE project_latest (
      object_id TEXT, created_at TEXT, organization_reference TEXT, name TEXT, user_git_repo_url TEXT,
      is_path_accessible INTEGER, is_deleted INTEGER, default_system_prompt TEXT, workspace_setup_command TEXT, naming_pattern TEXT
    );
    CREATE TABLE workspace_latest (
      object_id TEXT, created_at TEXT, project_id TEXT, organization_reference TEXT, description TEXT,
      initialization_strategy TEXT, source_branch TEXT, target_branch TEXT, environment_id TEXT, source_git_hash TEXT,
      is_deleted INTEGER, is_open INTEGER, setup_command_triggered INTEGER, setup_status TEXT, setup_run_id TEXT,
      setup_command TEXT, setup_exit_code INTEGER, setup_started_at REAL, setup_finished_at REAL, setup_log_path TEXT,
      setup_log_truncated INTEGER, diff_status TEXT, diff_updated_at TEXT, requested_branch_name TEXT
    );
    CREATE TABLE task_latest (
      object_id TEXT, created_at TEXT, organization_reference TEXT, user_reference TEXT, project_id TEXT,
      input_data TEXT, max_seconds REAL, current_state TEXT, outcome TEXT, error TEXT,
      is_deleted INTEGER, is_deleting INTEGER, last_read_at TEXT
    );
    CREATE TABLE saved_agent_message (object_id TEXT, created_at TEXT, task_id TEXT, message TEXT, source TEXT, is_partial INTEGER);
    CREATE TABLE notification (object_id TEXT, created_at TEXT, user_reference TEXT, message TEXT, importance TEXT, task_id TEXT, project_id TEXT);
  `);

  db.prepare("INSERT INTO user_settings_latest VALUES (?,?,?)").run(
    "usr_settings",
    "2026-01-01T00:00:00Z",
    "user-ref-1",
  );
  db.prepare("INSERT INTO project_latest VALUES (?,?,?,?,?,?,?,?,?,?)").run(
    "prj_1",
    "2026-01-02T00:00:00Z",
    "org-ref-1",
    "my-repo",
    "file:///Users/dev/my-repo",
    1,
    0,
    "be helpful",
    "make setup",
    "feat/{name}",
  );
  db.prepare(
    "INSERT INTO workspace_latest VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
  ).run(
    "ws_1",
    "2026-01-03T00:00:00Z",
    "prj_1",
    "org-ref-1",
    "a workspace",
    "WORKTREE",
    "main",
    "main",
    "env-123",
    "deadbeef",
    0,
    1,
    1,
    "succeeded",
    "run-1",
    "echo hi",
    0,
    1700.5,
    1800.5,
    "/logs/setup.log",
    0,
    "READY",
    "2026-01-03T01:00:00Z",
    "feat/x",
  );
  const inputData = JSON.stringify({
    object_type: "AgentTaskInputsV2",
    agent_config: { object_type: "ClaudeCodeSDKAgentConfig" },
    git_hash: "abc123hash",
    system_prompt: "you are helpful",
    default_model: "CLAUDE-4-OPUS",
  });
  const currentState = JSON.stringify({
    object_type: "AgentTaskStateV2",
    last_processed_message_id: "agm_last",
    title: "Fix the bug",
    workspace_id: "ws_1",
    terminal_session_id: "sess-xyz",
    terminal_shell_pid: 4242,
    available_models: [
      {
        provider: "anthropic",
        model_id: "CLAUDE-4-OPUS",
        display_name: "Opus",
      },
    ],
    current_model: {
      provider: "anthropic",
      model_id: "CLAUDE-4-OPUS",
      display_name: "Opus",
    },
  });
  db.prepare("INSERT INTO task_latest VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)").run(
    AGENT_ID,
    "2026-01-04T00:00:00Z",
    "org-ref-1",
    "user-ref-1",
    "prj_1",
    inputData,
    null,
    currentState,
    "RUNNING",
    null,
    0,
    0,
    "2026-01-04T02:00:00Z",
  );
  db.prepare("INSERT INTO saved_agent_message VALUES (?,?,?,?,?,?)").run(
    "agm_1",
    "2026-01-04T00:01:00Z",
    AGENT_ID,
    JSON.stringify({ object_type: "ChatInputUserMessage", text: "hi" }),
    "USER",
    0,
  );
  db.prepare("INSERT INTO notification VALUES (?,?,?,?,?,?,?)").run(
    "ntf_1",
    "2026-01-04T00:02:00Z",
    "user-ref-1",
    "Agent needs input",
    "ACTIVE",
    AGENT_ID,
    "prj_1",
  );
  db.close();
}

describe("migration seed -> migrate -> verify", () => {
  let dir: string;
  let sourceDb: string;
  let targetDb: string;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-migrate-"));
    sourceDb = path.join(dir, "old.db");
    targetDb = path.join(dir, "new.db");
    seedOldStore(sourceDb);
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("migrates all six entities, preserving IDs and flattening the agent", () => {
    const summary = migrateDatabase({
      sourceDbPath: sourceDb,
      targetDbPath: targetDb,
      migrationsFolder: MIGRATIONS_FOLDER,
    });
    expect(summary).toEqual({
      userSettings: 1,
      repos: 1,
      workspaces: 1,
      agents: 1,
      agentMessages: 1,
      notifications: 1,
    });

    const orm = createOrm(openDatabase(targetDb));

    const repo = getRepo(orm, "prj_1");
    expect(repo).toMatchObject({
      objectId: "prj_1",
      name: "my-repo",
      isDeleted: false,
      defaultSystemPrompt: "be helpful",
    });

    const workspace = getWorkspace(orm, "ws_1");
    expect(workspace).toMatchObject({
      objectId: "ws_1",
      projectId: "prj_1",
      initializationStrategy: "WORKTREE",
      isOpen: true,
      setupExitCode: 0,
    });

    // The tsk_ id is preserved VERBATIM (on-disk paths / --resume depend on it).
    const agent = getAgent(orm, AGENT_ID);
    expect(agent).toMatchObject({
      objectId: AGENT_ID,
      projectId: "prj_1",
      workspaceId: "ws_1",
      runState: "RUNNING", // outcome -> run_state
      startingGitHash: "abc123hash",
      systemPrompt: "you are helpful",
      defaultModel: "CLAUDE-4-OPUS",
      title: "Fix the bug",
      lastProcessedMessageId: "agm_last",
      terminalSessionId: "sess-xyz", // session id carried into the new column
      terminalShellPid: 4242,
    });
    expect(agent?.agentConfig).toEqual({
      object_type: "ClaudeCodeSDKAgentConfig",
    });
    expect(agent?.availableModels).toHaveLength(1);

    expect(getAgentMessage(orm, "agm_1")).toMatchObject({
      objectId: "agm_1",
      agentId: AGENT_ID,
      source: "USER",
      isPartial: false,
    });
    expect(getNotification(orm, "ntf_1")).toMatchObject({
      objectId: "ntf_1",
      agentId: AGENT_ID,
      projectId: "prj_1",
      importance: "ACTIVE",
    });
    expect(getUserSettings(orm)?.objectId).toBe("usr_settings");
  });

  it("leaves config.toml byte-for-byte untouched", () => {
    const configToml = path.join(dir, "config.toml");
    const original =
      'user_email = "dev@example.com"\nis_product_analytics_enabled = true\n';
    writeFileSync(configToml, original);
    migrateDatabase({
      sourceDbPath: sourceDb,
      targetDbPath: targetDb,
      migrationsFolder: MIGRATIONS_FOLDER,
    });
    expect(readFileSync(configToml, "utf8")).toBe(original);
  });

  it("fails loud on a store that already has new-schema tables", () => {
    const db = new Database(sourceDb);
    db.exec("CREATE TABLE agent (object_id TEXT)");
    db.close();
    expect(() =>
      migrateDatabase({
        sourceDbPath: sourceDb,
        targetDbPath: targetDb,
        migrationsFolder: MIGRATIONS_FOLDER,
      }),
    ).toThrow(/already.*new-schema|already-migrated|newer/i);
  });
});
