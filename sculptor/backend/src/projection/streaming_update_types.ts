// Wire types for the `StreamingUpdate` projection and ALL its sub-objects.
//
// These mirror the Python wire contract field-for-field (RW-API-3): the
// frontend merges deltas by these exact keys, so the names and nesting MUST
// match. Each type below cites the Python source it was matched against.
//
// Ported from:
//   - `StreamingUpdate`        — sculptor/sculptor/web/streams.py L321-338
//   - `TaskUpdate`             — sculptor/sculptor/web/derived.py L744-808
//   - `UserUpdate`             — sculptor/sculptor/web/derived.py L811-816
//   - `DependenciesStatus`     — sculptor/sculptor/web/data_types.py L677-682
//   - `WorkspaceSetupStatus`   — sculptor/sculptor/web/data_types.py L685-694
//   - `WorkspaceSetupOutputChunk` — sculptor/sculptor/web/data_types.py L697-707
//   - `BtwUpdate`              — sculptor/sculptor/web/data_types.py L721-729
//   - `OpenFileUiAction`       — sculptor/sculptor/web/data_types.py L732-735
//   - `WebviewCommandUiAction` — sculptor/sculptor/web/data_types.py L738-742
//   - `WorkspaceBranchInfo` / `WorkspaceRemoteBranchesInfo` / `PrStatusInfo`
//                              — sculptor/sculptor/web/derived.py
//
// NOTE: the keyed dicts are wire objects (`dict[WorkspaceID, ...]`); on the wire
// the keys are the string ids. We model them as `Record<string, ...>`.

import type { ChatMessage } from "~/projection/chat_types";
import type { CodingAgentTaskView } from "~/projection/view_types";

// --- UserUpdate sub-entities -----------------------------------------------
//
// `UserUpdate` carries the changed data-model rows directly. The Python wire
// shape serializes the full Project/Workspace/Notification/UserSettings models;
// the rewrite serializes the equivalent rows (the API layer, Phase 6, owns the
// internal repo->project wire-name mapping). Here we model the wire-facing
// fields the frontend reads off `user_update`.

// Project (the `repo` table; serialized as `project` on the wire — repo.ts).
// sculptor/sculptor/database/models.py:Project (L44-68).
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

// Workspace. sculptor/sculptor/database/models.py:Workspace (L81-116).
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

// Notification. sculptor/sculptor/database/models.py:Notification (L341-351).
export interface WireNotification {
  object_id: string;
  message: string;
  importance: string;
  task_id: string | null;
  project_id: string | null;
}

// UserSettings. sculptor/sculptor/database/models.py:UserSettings (L37-41).
// Holds essentially nothing in the rewrite (user_settings.ts).
export interface WireUserSettings {
  object_id: string;
}

// Server settings (SculptorSettings, sculptor/sculptor/config/settings.py L29).
// Carried opaquely here; the config endpoint (Phase 6) owns its full shape.
export type WireServerSettings = Record<string, unknown>;

// UserUpdate — derived.py L811-816. The ONLY delivery path for notifications
// and for live project-list / workspace-list / settings changes. ScopeAll-only
// (project_for_scope drops it for narrower scopes — streams.py L427).
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
// derived.py L744-808. The incremental per-task chat update the frontend merges
// (chat_messages append, in_progress replace, queued replace). The rewrite's
// warm cache (Task 4.4) produces this from the Task 4.2 fold state. Fields the
// fold does not yet track (artifacts, streaming bookkeeping that lives inside
// the fold) are defaulted to wire-faithful empties here.
export interface TaskUpdate {
  task_id: string;
  // derived.py L768: only new completed messages; frontend appends.
  chat_messages: ChatMessage[];
  // derived.py L769: changed artifacts (frontend re-fetches). Not produced yet.
  updated_artifacts: unknown[];
  // derived.py L770: full in-progress message; frontend replaces.
  in_progress_chat_message: ChatMessage | null;
  // derived.py L771: full queue; frontend replaces.
  queued_chat_messages: ChatMessage[];
  in_progress_user_message_id: string | null;
  streaming_start_index: number;
  is_streaming_active: boolean;
  in_progress_message_was_streamed: boolean;
  streamed_assistant_message_ids: string[];
  streamed_segment_first_response_id: string | null;
  // derived.py L793: the unanswered AskUserQuestion data (or null).
  pending_user_question: AskUserQuestionWire | null;
  submitted_question_answers: Record<string, SubmittedQuestionAnswersWire>;
  is_in_plan_mode: boolean;
  pending_turn_metrics: unknown | null;
  // derived.py L808: background tasks awaiting their notification.
  pending_background_task_ids: string[];
}

// AskUserQuestionData on the wire (chat_types.AskUserQuestionData mirror).
export type AskUserQuestionWire = {
  questions: unknown[];
  tool_use_id: string;
  plan_file_path: string | null;
};

// SubmittedQuestionAnswers — derived.py L738-741.
export interface SubmittedQuestionAnswersWire {
  question_data: AskUserQuestionWire;
  answers: Record<string, string>;
  tool_use_id: string;
}

// --- DependenciesStatus ----------------------------------------------------
//
// data_types.py L677-682 (DependenciesStatus) + L619-639 (DependencyInfo) +
// L595-603 (VersionRangeInfo) + L606-611 (InstallProgress). Pushed live over
// the stream (deduped — streams.py L646-649). ScopeAll-only.
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
// derived.py: WorkspaceBranchInfo / WorkspaceRemoteBranchesInfo / PrStatusInfo.
// The producing services (repo polling, PR polling) land in Phase 7; the
// snapshot leaves these dicts empty until then. We model the fields the
// frontend reads so the delta path is type-safe once those services publish.

// WorkspaceBranchInfo — derived.py (current branch + workspace id, used by
// _notify_pr_polling_service in streams.py L742-754).
export interface WorkspaceBranchInfo {
  workspace_id: string;
  current_branch: string;
  // Additional branch metadata the service fills; carried opaquely for now.
  [key: string]: unknown;
}

// WorkspaceRemoteBranchesInfo — derived.py.
export interface WorkspaceRemoteBranchesInfo {
  workspace_id: string;
  [key: string]: unknown;
}

// PrStatusInfo — derived.py. Phase 7 PR polling populates this.
export interface PrStatusInfo {
  workspace_id: string;
  [key: string]: unknown;
}

// --- Workspace setup sub-shapes --------------------------------------------

// WorkspaceSetupStatus — data_types.py L685-694.
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

// WorkspaceSetupOutputChunk — data_types.py L697-707. `data` is raw bytes,
// base64-encoded on the wire; modeled here as the base64 string.
export interface WorkspaceSetupOutputChunk {
  workspace_id: string;
  run_id: string;
  seq: number;
  data: string;
}

// --- BtwUpdate -------------------------------------------------------------
//
// data_types.py L721-729. `/btw` side-chat replies arrive over the stream too.
export interface BtwUpdate {
  workspace_id: string;
  agent_id: string;
  request_id: string;
  state: "running" | "done" | "error" | "aborted";
  answer: string;
  error_message: string | null;
}

// --- UI action sub-shapes --------------------------------------------------

// OpenFileUiAction — data_types.py L732-735.
export interface OpenFileUiAction {
  workspace_id: string;
  file_path: string;
  mode: "auto" | "diff" | "file";
}

// WebviewCommandUiAction — data_types.py L738-742.
export interface WebviewCommandUiAction {
  workspace_id: string;
  seq: number;
  kind: "navigate" | "refresh";
  url: string | null;
}

// --- StreamingUpdate -------------------------------------------------------
//
// streams.py L321-338. The wire object. Snapshot-then-delta semantics
// (REQ-NFR-001): a connect MUST receive a full snapshot before any delta.
// `user_update` / `finished_request_ids` / `dependencies_status` / `btw_update`
// are NOT per-workspace keyed and are easy to miss — do NOT drop them.
export interface StreamingUpdate {
  // streams.py L322-323
  task_update_by_task_id: Record<string, TaskUpdate>;
  task_views_by_task_id: Record<string, CodingAgentTaskView>;
  // streams.py L324 — ScopeAll-only.
  user_update: UserUpdate;
  // streams.py L325-329
  workspace_branch_by_workspace_id: Record<string, WorkspaceBranchInfo | null>;
  workspace_remote_branches_by_workspace_id: Record<string, WorkspaceRemoteBranchesInfo | null>;
  pr_status_by_workspace_id: Record<string, PrStatusInfo | null>;
  // streams.py L330 — request-completion signal; ScopeAll-only.
  finished_request_ids: string[];
  // streams.py L331 — ScopeAll-only; deduped (L646-649).
  dependencies_status: DependenciesStatus | null;
  // streams.py L332-335
  workspace_setup_status_by_workspace_id: Record<string, WorkspaceSetupStatus>;
  workspace_setup_output_by_workspace_id: Record<string, WorkspaceSetupOutputChunk[]>;
  // streams.py L336 — ScopeAll/per-agent; `/btw` reply.
  btw_update: BtwUpdate | null;
  // streams.py L337-338
  ui_open_file_by_workspace_id: Record<string, OpenFileUiAction>;
  ui_webview_command_by_workspace_id: Record<string, WebviewCommandUiAction>;
}

// A fully-empty StreamingUpdate (matches `StreamingUpdate()` default ctor —
// streams.py L321-338). Used as the base for both snapshots and deltas.
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
