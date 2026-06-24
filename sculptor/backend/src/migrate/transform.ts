import type {
  NewAgentMessageRow,
  NewAgentRow,
  NewNotificationRow,
  NewRepoRow,
  NewUserSettingsRow,
  NewWorkspaceRow,
} from "~/db/schema";
import type {
  AgentMessageSource,
  NotificationImportance,
  RunState,
  WorkspaceInitializationStrategy,
} from "~/db/schema/enums";
import type { OldStore, RawRow } from "~/migrate/read_old_db";

// Maps old Python-schema rows to the new Drizzle-schema rows. IDs are preserved
// VERBATIM (esp. tsk_… agent ids, which appear in on-disk paths / --resume), the
// multi-tenancy columns (organization_reference / user_reference) are dropped,
// outcome -> run_state, and the AgentTaskInputsV2 / AgentTaskStateV2 JSON is
// flattened into the new `agent` columns. Claude/Pi session ids live in on-disk
// state files (preserved in place), not the DB, so they migrate as null.

export interface NewStore {
  userSettings: NewUserSettingsRow[];
  repos: NewRepoRow[];
  workspaces: NewWorkspaceRow[];
  agents: NewAgentRow[];
  agentMessages: NewAgentMessageRow[];
  notifications: NewNotificationRow[];
}

function bool(value: unknown): boolean {
  return value === 1 || value === true || value === "1";
}

function str(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function parseJson(value: unknown): Record<string, unknown> | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    return JSON.parse(value) as Record<string, unknown>;
  }
  return value as Record<string, unknown>;
}

function transformRepo(row: RawRow): NewRepoRow {
  return {
    objectId: String(row.object_id),
    createdAt: String(row.created_at),
    name: String(row.name),
    userGitRepoUrl: str(row.user_git_repo_url),
    isPathAccessible: bool(row.is_path_accessible),
    isDeleted: bool(row.is_deleted),
    defaultSystemPrompt: str(row.default_system_prompt),
    workspaceSetupCommand: str(row.workspace_setup_command),
    namingPattern: str(row.naming_pattern),
  };
}

function transformWorkspace(row: RawRow): NewWorkspaceRow {
  return {
    objectId: String(row.object_id),
    createdAt: String(row.created_at),
    projectId: String(row.project_id),
    description: String(row.description),
    initializationStrategy: String(
      row.initialization_strategy,
    ) as WorkspaceInitializationStrategy,
    sourceBranch: str(row.source_branch),
    targetBranch: str(row.target_branch),
    environmentId: str(row.environment_id),
    sourceGitHash: str(row.source_git_hash),
    isDeleted: bool(row.is_deleted),
    isOpen: bool(row.is_open),
    setupCommandTriggered: bool(row.setup_command_triggered),
    setupStatus: String(row.setup_status),
    setupRunId: str(row.setup_run_id),
    setupCommand: str(row.setup_command),
    setupExitCode: num(row.setup_exit_code),
    setupStartedAt: num(row.setup_started_at),
    setupFinishedAt: num(row.setup_finished_at),
    setupLogPath: str(row.setup_log_path),
    setupLogTruncated: bool(row.setup_log_truncated),
    diffStatus: String(row.diff_status) as NewWorkspaceRow["diffStatus"],
    diffUpdatedAt: str(row.diff_updated_at),
    requestedBranchName: str(row.requested_branch_name),
  };
}

function transformAgent(row: RawRow): NewAgentRow {
  const input = parseJson(row.input_data) ?? {};
  const state = parseJson(row.current_state) ?? {};
  const agentConfig = (input.agent_config as
    | Record<string, unknown>
    | undefined) ?? { object_type: "TerminalAgentConfig" };
  return {
    objectId: String(row.object_id),
    createdAt: String(row.created_at),
    projectId: String(row.project_id),
    workspaceId: str(state.workspace_id),
    agentConfig,
    startingGitHash: str(input.git_hash),
    systemPrompt: str(input.system_prompt),
    defaultModel: str(input.default_model),
    runState: String(row.outcome) as RunState,
    error: parseJson(row.error),
    title: str(state.title),
    lastProcessedMessageId: str(state.last_processed_message_id),
    // Claude/Pi session ids resume from on-disk state files (preserved), not DB.
    claudeSessionId: null,
    piSessionId: null,
    terminalSessionId: str(state.terminal_session_id),
    terminalShellPid: num(state.terminal_shell_pid),
    availableModels: Array.isArray(state.available_models)
      ? (state.available_models as Record<string, unknown>[])
      : [],
    currentModel:
      (state.current_model as Record<string, unknown> | undefined) ?? null,
    isDeleted: bool(row.is_deleted),
    isDeleting: bool(row.is_deleting),
    lastReadAt: str(row.last_read_at),
  };
}

function transformMessage(row: RawRow): NewAgentMessageRow {
  return {
    objectId: String(row.object_id),
    createdAt: String(row.created_at),
    agentId: String(row.task_id),
    message: parseJson(row.message) ?? {},
    source: String(row.source) as AgentMessageSource,
    isPartial: bool(row.is_partial),
  };
}

function transformNotification(row: RawRow): NewNotificationRow {
  return {
    objectId: String(row.object_id),
    createdAt: String(row.created_at),
    message: String(row.message),
    importance: String(row.importance) as NotificationImportance,
    agentId: str(row.task_id),
    projectId: str(row.project_id),
  };
}

function transformUserSettings(row: RawRow): NewUserSettingsRow {
  return { objectId: String(row.object_id), createdAt: String(row.created_at) };
}

export function transformStore(old: OldStore): NewStore {
  return {
    userSettings: old.userSettings.map(transformUserSettings),
    repos: old.projects.map(transformRepo),
    workspaces: old.workspaces.map(transformWorkspace),
    agents: old.tasks.map(transformAgent),
    agentMessages: old.messages.map(transformMessage),
    notifications: old.notifications.map(transformNotification),
  };
}
