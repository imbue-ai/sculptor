// TypeScript types for the derived, UI-facing per-agent view.
//
// Ported from `sculptor/sculptor/web/derived.py` (the `TaskStatus` enum and the
// `CodingAgentTaskView` computed fields). These shapes are the frontend contract
// (RW-API-3): the per-agent `status` and the view fields the streaming snapshot
// (Task 4.4) carries. The derived UI `status` is DISTINCT from the stored
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

// The derived per-agent view computed in `computeAgentView`. The field names and
// shapes mirror the `CodingAgentTaskView` computed fields the frontend reads.
// (The full Python view carries additional fields sourced from settings / the
// harness registry — model switcher, harness capabilities, workspace_peek, etc.
// — which are computed elsewhere in the rewrite; this view holds the
// message-derived fields owned by Task 4.3.)
export interface CodingAgentTaskView {
  object_type: "CodingAgentTaskView";
  status: TaskStatus;
  // The agent's persisted title (AgentTaskStateV2.title), or null.
  title: string | null;
  // First ChatInputUserMessage text; "" until the first user message arrives.
  goal: string;
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
