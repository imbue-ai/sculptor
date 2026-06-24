// The typed event taxonomy — one variant per StreamingUpdate field source in
// web/streams.py. Every event carries the owning scope ids (project/workspace/
// agent) so the projection's scope narrowing (Task 4.5) is a pure filter.
// Payloads are kept minimal: the projection reads current state from the
// repositories / warm cache (Task 4.4) rather than carrying full snapshots —
// the exceptions are events whose data is itself the thing to fold (the new
// message, a setup-output chunk, the dependency status, the btw update, and the
// data-model change's request id + changed rows).

// Drives task_update_by_task_id: a new agent_message row to fold into the chat
// (the partial-chunk folding in Task 4.2 depends on emit order).
export interface AgentMessageEvent {
  kind: "agent_message";
  agentId: string;
  workspaceId?: string;
  projectId?: string;
  message: Record<string, unknown>;
}

// Drives task_views_by_task_id: the agent's run-state / view changed.
export interface AgentStatusEvent {
  kind: "agent_status";
  agentId: string;
  workspaceId?: string;
  projectId?: string;
}

// Drives user_update + finished_request_ids. ScopeAll-only (user_update is
// dropped for scoped connections). The ONLY source of notifications and of live
// project/workspace/settings changes — Phase 6 mutation paths publish it. It
// carries the originating request id and the changed entity refs.
export interface ChangedEntityRef {
  type: "repo" | "workspace" | "agent" | "notification" | "user_settings";
  id: string;
}

export interface DataModelChangeEvent {
  kind: "data_model_change";
  requestId?: string | null;
  changedEntities?: ChangedEntityRef[];
}

// Drives workspace_branch_by_workspace_id.
export interface WorkspaceBranchEvent {
  kind: "workspace_branch";
  workspaceId: string;
  projectId?: string;
}

// Drives workspace_remote_branches_by_workspace_id.
export interface WorkspaceRemoteBranchesEvent {
  kind: "workspace_remote_branches";
  workspaceId: string;
  projectId?: string;
}

// Drives pr_status_by_workspace_id.
export interface PrStatusEvent {
  kind: "pr_status";
  workspaceId: string;
  projectId?: string;
}

// Drives dependencies_status. ScopeAll-only.
export interface DependenciesStatusEvent {
  kind: "dependencies_status";
  status: Record<string, unknown> | null;
}

// Drives workspace_setup_status_by_workspace_id. Carries the WorkspaceSetupStatus
// snapshot the setup runner (Task 6.4) produces on each state transition.
export interface WorkspaceSetupStatusEvent {
  kind: "workspace_setup_status";
  workspaceId: string;
  projectId?: string;
  status: Record<string, unknown>;
}

// Drives workspace_setup_output_by_workspace_id: a chunk of setup-command output.
export interface WorkspaceSetupOutputEvent {
  kind: "workspace_setup_output";
  workspaceId: string;
  projectId?: string;
  chunk: Record<string, unknown>;
}

// Drives btw_update (read-only side-question results, Tasks 6.8/7.4).
export interface BtwUpdateEvent {
  kind: "btw_update";
  agentId?: string;
  workspaceId?: string;
  projectId?: string;
  update: Record<string, unknown>;
}

// Drives ui_open_file_by_workspace_id.
export interface UiOpenFileEvent {
  kind: "ui_open_file";
  workspaceId: string;
  projectId?: string;
  action: Record<string, unknown>;
}

// Drives ui_webview_command_by_workspace_id.
export interface UiWebviewCommandEvent {
  kind: "ui_webview_command";
  workspaceId: string;
  projectId?: string;
  command: Record<string, unknown>;
}

export type BusEvent =
  | AgentMessageEvent
  | AgentStatusEvent
  | DataModelChangeEvent
  | WorkspaceBranchEvent
  | WorkspaceRemoteBranchesEvent
  | PrStatusEvent
  | DependenciesStatusEvent
  | WorkspaceSetupStatusEvent
  | WorkspaceSetupOutputEvent
  | BtwUpdateEvent
  | UiOpenFileEvent
  | UiWebviewCommandEvent;

export type BusEventKind = BusEvent["kind"];

// The kinds with no per-workspace key — user_update / dependencies_status are
// dropped for scoped (non-ScopeAll) connections (Task 4.5 applies this).
export const SCOPE_ALL_ONLY_EVENT_KINDS: ReadonlySet<BusEventKind> =
  new Set<BusEventKind>(["data_model_change", "dependencies_status"]);
