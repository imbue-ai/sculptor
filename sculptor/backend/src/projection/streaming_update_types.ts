// Wire types for the `StreamingUpdate` projection and ALL its sub-objects.
//
// These mirror the Python wire contract field-for-field: the frontend merges
// deltas by these exact keys, so the names and nesting MUST match. Each type
// below names the Python model it was matched against:
// `StreamingUpdate`, `TaskUpdate`, `UserUpdate`, `DependenciesStatus`,
// `WorkspaceSetupStatus`, `WorkspaceSetupOutputChunk`, `BtwUpdate`,
// `OpenFileUiAction`, `WebviewCommandUiAction`, `WorkspaceBranchInfo`,
// `WorkspaceRemoteBranchesInfo`, `PrStatusInfo`.
//
// NOTE: the keyed dicts are wire objects (`dict[WorkspaceID, ...]`); on the wire
// the keys are the string ids. We model them as `Record<string, ...>`.

import type { ChatMessage } from "~/projection/chat_types";
import type { CodingAgentTaskView } from "~/projection/view_types";

// --- UserUpdate sub-entities -----------------------------------------------
//
// `UserUpdate` carries the changed data-model rows directly. The Python wire
// shape serializes the full Project/Workspace/Notification/UserSettings models;
// the rewrite serializes the equivalent rows (the API layer owns the internal
// repo->project wire-name mapping). Here we model the wire-facing fields the
// frontend reads off `user_update`.

// Project (the `repo` table; serialized as `project` on the wire — repo.ts).
// Mirrors the Python `Project` model.
export interface WireProject {
  object_id: string;
  name: string;
  user_git_repo_url: string | null;
  is_path_accessible: boolean;
  is_deleted: boolean;
  default_system_prompt: string | null;
  workspace_setup_command: string | null;
  naming_pattern: string | null;
}

// Workspace. Mirrors the Python `Workspace` model.
export interface WireWorkspace {
  object_id: string;
  project_id: string;
  description: string;
  initialization_strategy: string;
  source_branch: string | null;
  target_branch: string | null;
  environment_id: string | null;
  source_git_hash: string | null;
  is_deleted: boolean;
  is_open: boolean;
  setup_command_triggered: boolean;
  setup_status: string;
  setup_run_id: string | null;
  setup_command: string | null;
  setup_exit_code: number | null;
  setup_started_at: number | null;
  setup_finished_at: number | null;
  setup_log_path: string | null;
  setup_log_truncated: boolean;
  diff_status: string;
  diff_updated_at: string | null;
  requested_branch_name: string | null;
}

// Notification. Mirrors the Python `Notification` model.
export interface WireNotification {
  object_id: string;
  message: string;
  importance: string;
  task_id: string | null;
  project_id: string | null;
}

// UserSettings. Mirrors the Python `UserSettings` model. Holds essentially
// nothing in the rewrite (user_settings.ts).
export interface WireUserSettings {
  object_id: string;
}

// Server settings (SculptorSettings). Carried opaquely here; the config endpoint
// owns its full shape.
export type WireServerSettings = Record<string, unknown>;

// UserUpdate. The ONLY delivery path for notifications and for live project-list
// / workspace-list / settings changes. ScopeAll-only (project_for_scope drops it
// for narrower scopes).
export interface UserUpdate {
  user_settings: WireUserSettings | null;
  projects: WireProject[];
  workspaces: WireWorkspace[];
  settings: WireServerSettings | null;
  notifications: WireNotification[];
}

export function emptyUserUpdate(): UserUpdate {
  return {
    user_settings: null,
    projects: [],
    workspaces: [],
    settings: null,
    notifications: [],
  };
}

// --- TaskUpdate ------------------------------------------------------------
//
// The incremental per-task chat update the frontend merges (chat_messages
// append, in_progress replace, queued replace). The rewrite's warm cache
// produces this from the fold state. Fields the fold does not yet track
// (artifacts, streaming bookkeeping that lives inside the fold) are defaulted to
// wire-faithful empties here.
export interface TaskUpdate {
  task_id: string;
  // Only new completed messages; frontend appends.
  chat_messages: ChatMessage[];
  // Changed artifacts (frontend re-fetches). Not produced yet.
  updated_artifacts: unknown[];
  // Full in-progress message; frontend replaces.
  in_progress_chat_message: ChatMessage | null;
  // Full queue; frontend replaces.
  queued_chat_messages: ChatMessage[];
  in_progress_user_message_id: string | null;
  streaming_start_index: number;
  is_streaming_active: boolean;
  in_progress_message_was_streamed: boolean;
  streamed_assistant_message_ids: string[];
  streamed_segment_first_response_id: string | null;
  // The unanswered AskUserQuestion data (or null).
  pending_user_question: AskUserQuestionWire | null;
  submitted_question_answers: Record<string, SubmittedQuestionAnswersWire>;
  is_in_plan_mode: boolean;
  pending_turn_metrics: unknown | null;
  // Background tasks awaiting their notification.
  pending_background_task_ids: string[];
}

// AskUserQuestionData on the wire (chat_types.AskUserQuestionData mirror).
export type AskUserQuestionWire = {
  questions: unknown[];
  tool_use_id: string;
  plan_file_path: string | null;
};

// SubmittedQuestionAnswers.
export interface SubmittedQuestionAnswersWire {
  question_data: AskUserQuestionWire;
  answers: Record<string, string>;
  tool_use_id: string;
}

// --- DependenciesStatus ----------------------------------------------------
//
// Mirrors DependenciesStatus + DependencyInfo + VersionRangeInfo +
// InstallProgress. Pushed live over the stream (deduped). ScopeAll-only.
export interface VersionRangeInfo {
  min_version: string;
  max_version: string;
  recommended_version: string;
}

export interface InstallProgress {
  tool: string;
  bytes_downloaded: number;
  total_bytes: number | null;
}

export interface DependencyInfo {
  installed: boolean;
  path: string | null;
  version: string | null;
  is_override: boolean;
  mode: string | null;
  version_range: VersionRangeInfo | null;
  is_version_in_range: boolean | null;
  managed_version: string | null;
  is_authenticated: boolean | null;
  install_progress: InstallProgress | null;
  install_error: string | null;
}

export interface DependenciesStatus {
  git: DependencyInfo;
  claude: DependencyInfo;
  pi: DependencyInfo;
}

// --- Workspace branch / PR sub-shapes --------------------------------------
//
// WorkspaceBranchInfo / WorkspaceRemoteBranchesInfo / PrStatusInfo. The
// producing services (repo polling, PR polling) leave these dicts empty until
// they publish; we model the fields the frontend reads so the delta path is
// type-safe once those services come online.

// WorkspaceBranchInfo (current branch + workspace id, used by the PR polling
// notification path).
export interface WorkspaceBranchInfo {
  workspace_id: string;
  current_branch: string;
  // Additional branch metadata the service fills; carried opaquely for now.
  [key: string]: unknown;
}

// WorkspaceRemoteBranchesInfo.
export interface WorkspaceRemoteBranchesInfo {
  workspace_id: string;
  [key: string]: unknown;
}

// PrStatusInfo. The PR polling service populates this.
export interface PrStatusInfo {
  workspace_id: string;
  [key: string]: unknown;
}

// --- Workspace setup sub-shapes --------------------------------------------

// WorkspaceSetupStatus.
export type WorkspaceSetupStatusValue =
  | "not_configured"
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "legacy";

export interface WorkspaceSetupStatus {
  workspace_id: string;
  status: WorkspaceSetupStatusValue;
  run_id: string | null;
  exit_code: number | null;
  started_at: number | null;
  finished_at: number | null;
  log_truncated: boolean;
}

// WorkspaceSetupOutputChunk. `data` is raw bytes,
// base64-encoded on the wire; modeled here as the base64 string.
export interface WorkspaceSetupOutputChunk {
  workspace_id: string;
  run_id: string;
  seq: number;
  data: string;
}

// --- BtwUpdate -------------------------------------------------------------
//
// BtwUpdate. `/btw` side-chat replies arrive over the stream too.
export interface BtwUpdate {
  workspace_id: string;
  agent_id: string;
  request_id: string;
  state: "running" | "done" | "error" | "aborted";
  answer: string;
  error_message: string | null;
}

// --- UI action sub-shapes --------------------------------------------------

// OpenFileUiAction.
export interface OpenFileUiAction {
  workspace_id: string;
  file_path: string;
  mode: "auto" | "diff" | "file";
}

// WebviewCommandUiAction.
export interface WebviewCommandUiAction {
  workspace_id: string;
  seq: number;
  kind: "navigate" | "refresh";
  url: string | null;
}

// --- StreamingUpdate -------------------------------------------------------
//
// The wire object. Snapshot-then-delta semantics: a connect MUST receive a full
// snapshot before any delta. `user_update` / `finished_request_ids` /
// `dependencies_status` / `btw_update` are NOT per-workspace keyed and are easy
// to miss — do NOT drop them.
export interface StreamingUpdate {
  task_update_by_task_id: Record<string, TaskUpdate>;
  task_views_by_task_id: Record<string, CodingAgentTaskView>;
  // ScopeAll-only.
  user_update: UserUpdate;
  workspace_branch_by_workspace_id: Record<string, WorkspaceBranchInfo | null>;
  workspace_remote_branches_by_workspace_id: Record<string, WorkspaceRemoteBranchesInfo | null>;
  pr_status_by_workspace_id: Record<string, PrStatusInfo | null>;
  // Request-completion signal; ScopeAll-only.
  finished_request_ids: string[];
  // ScopeAll-only; deduped.
  dependencies_status: DependenciesStatus | null;
  workspace_setup_status_by_workspace_id: Record<string, WorkspaceSetupStatus>;
  workspace_setup_output_by_workspace_id: Record<string, WorkspaceSetupOutputChunk[]>;
  // ScopeAll/per-agent; `/btw` reply.
  btw_update: BtwUpdate | null;
  ui_open_file_by_workspace_id: Record<string, OpenFileUiAction>;
  ui_webview_command_by_workspace_id: Record<string, WebviewCommandUiAction>;
}

// A fully-empty StreamingUpdate (matches the Python `StreamingUpdate()` default
// ctor). Used as the base for both snapshots and deltas.
export function emptyStreamingUpdate(): StreamingUpdate {
  return {
    task_update_by_task_id: {},
    task_views_by_task_id: {},
    user_update: emptyUserUpdate(),
    workspace_branch_by_workspace_id: {},
    workspace_remote_branches_by_workspace_id: {},
    pr_status_by_workspace_id: {},
    finished_request_ids: [],
    dependencies_status: null,
    workspace_setup_status_by_workspace_id: {},
    workspace_setup_output_by_workspace_id: {},
    btw_update: null,
    ui_open_file_by_workspace_id: {},
    ui_webview_command_by_workspace_id: {},
  };
}
