import { z } from "zod";

// SQLite has no native enum type; these are stored as text columns and guarded
// by the Zod schemas at the query boundary. Values mirror the Python
// UpperCaseStrEnums in sculptor/sculptor/database/workspace_enums.py.

export const WORKSPACE_INITIALIZATION_STRATEGIES = ["IN_PLACE", "CLONE", "WORKTREE"] as const;
export type WorkspaceInitializationStrategy = (typeof WORKSPACE_INITIALIZATION_STRATEGIES)[number];
export const workspaceInitializationStrategySchema = z.enum(WORKSPACE_INITIALIZATION_STRATEGIES);

export const DIFF_STATUSES = ["NONE", "GENERATING", "READY"] as const;
export type DiffStatus = (typeof DIFF_STATUSES)[number];
export const diffStatusSchema = z.enum(DIFF_STATUSES);

// The agent run lifecycle, mirroring TaskState in interfaces/agents/tasks.py.
// Stored as agent.run_state (the Python field was the misleadingly-named
// `outcome`). The UI-facing `status` is computed in the projection, not stored.
export const RUN_STATES = ["QUEUED", "RUNNING", "FAILED", "CANCELLED", "DELETED", "SUCCEEDED"] as const;
export type RunState = (typeof RUN_STATES)[number];
export const runStateSchema = z.enum(RUN_STATES);

// Mirrors AgentMessageSource in state/messages.py.
export const AGENT_MESSAGE_SOURCES = ["AGENT", "USER", "SCULPTOR_SYSTEM", "RUNNER"] as const;
export type AgentMessageSource = (typeof AGENT_MESSAGE_SOURCES)[number];
export const agentMessageSourceSchema = z.enum(AGENT_MESSAGE_SOURCES);

// Mirrors NotificationImportance in database/models.py.
export const NOTIFICATION_IMPORTANCES = ["PASSIVE", "ACTIVE", "TIME_SENSITIVE", "CRITICAL"] as const;
export type NotificationImportance = (typeof NOTIFICATION_IMPORTANCES)[number];
export const notificationImportanceSchema = z.enum(NOTIFICATION_IMPORTANCES);
