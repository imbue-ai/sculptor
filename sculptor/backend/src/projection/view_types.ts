// TypeScript types for the derived, UI-facing per-agent view.
//
// Ported from `sculptor/sculptor/web/derived.py` (the `TaskStatus` enum and the
// `CodingAgentTaskView` computed fields). These shapes are the frontend
// contract: the per-agent `status` and the view fields the streaming snapshot
// carries. The derived UI `status` is DISTINCT from the stored
// `agent.run_state` lifecycle (QUEUED/RUNNING/SUCCEEDED/...); do not conflate
// them.

// The derived UI status (NOT the stored run_state). Mirrors
// `derived.py:TaskStatus`.
//   BUILDING      — environment is being set up
//   RUNNING       — the agent process is actively running
//   READY         — completed successfully / idle
//   WAITING       — agent asked a question or is waiting for plan approval
//   ERROR         — process encountered an error (stderr output / failed run)
//   REQUEST_ERROR — last request failed (e.g. API 429) but the agent is usable
export const TASK_STATUSES = [
  "BUILDING",
  "RUNNING",
  "READY",
  "WAITING",
  "ERROR",
  "REQUEST_ERROR",
] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

// The stored task lifecycle (`run_state`), distinct from the derived UI status.
export const TASK_STATES = [
  "QUEUED",
  "RUNNING",
  "FAILED",
  "CANCELLED",
  "DELETED",
  "SUCCEEDED",
] as const;
export type TaskState = (typeof TASK_STATES)[number];

// The task interface kind (`derived.py:TaskInterface`).
export type TaskInterface = "TERMINAL" | "API";

// The peek/glance status the workspace tab shows (`WorkspacePeekAgentStatus`).
export const WORKSPACE_PEEK_AGENT_STATUSES = [
  "WORKING",
  "WAITING",
  "ERROR",
  "COMPLETED",
  "IDLE",
] as const;
export type WorkspacePeekAgentStatus =
  (typeof WORKSPACE_PEEK_AGENT_STATUSES)[number];

// The harness affordance flags the frontend uses to gate chat UI (HarnessCapabilities).
export interface HarnessCapabilities {
  supports_chat_interface: boolean;
  supports_interactive_backchannel: boolean;
  supports_skills: boolean;
  supports_sub_agents: boolean;
  supports_image_input: boolean;
  supports_fast_mode: boolean;
  supports_context_reset: boolean;
  supports_compaction: boolean;
  supports_background_tasks: boolean;
  supports_session_resume: boolean;
  supports_tool_use_rendering: boolean;
  supports_file_attachments: boolean;
  supports_interruption: boolean;
  supports_file_references: boolean;
  supports_model_selection: boolean;
}

// A selectable model the harness offers in its switcher (`ModelOption`).
export interface ModelOption {
  provider: string;
  model_id: string;
  display_name: string;
}

// The derived per-agent view computed in `computeAgentView`. The field names and
// shapes mirror the full `CodingAgentTaskView` the frontend reads: the
// message-derived status fields plus the agent-row / harness-registry fields
// (id, model switcher, harness capabilities, workspace_peek, lifecycle).
export interface CodingAgentTaskView {
  object_type: "CodingAgentTaskView";
  // The agent (task) id — the frontend reads this to navigate / key the tab.
  id: string;
  project_id: string;
  workspace_id: string | null;
  created_at: string;
  updated_at: string;
  // The stored lifecycle (run_state); distinct from the derived UI `status`.
  task_status: TaskState;
  // The agent's persisted title (AgentTaskStateV2.title), or null.
  title: string | null;
  title_or_something_like_it: string;
  // First ChatInputUserMessage text; "" until the first user message arrives.
  goal: string;
  initial_prompt: string;
  interface: TaskInterface;
  // The resolved model wire value (latest selection / creation default / fallback).
  model: string;
  selected_model_id: string | null;
  available_models: ModelOption[];
  harness_capabilities: HarnessCapabilities;
  accepts_automated_prompts: boolean;
  is_smooth_streaming_supported: boolean;
  is_auto_compacting: boolean;
  artifact_names: string[];
  is_deleted: boolean;
  last_read_at: string | null;
  workspace_peek_status: WorkspacePeekAgentStatus;
  status: TaskStatus;
  // Short human description of the agent's latest activity (present/past tense).
  current_activity: string | null;
  last_activity: string | null;
  // The latest v2 TaskListArtifact (PLAN) progress.
  task_completed: number;
  task_total: number;
  current_task_subject: string | null;
  // The unanswered question text (or "Waiting for plan approval"), when WAITING.
  waiting_detail: string | null;
  // The failure/error message, when ERROR / REQUEST_ERROR.
  error_detail: string | null;
}
