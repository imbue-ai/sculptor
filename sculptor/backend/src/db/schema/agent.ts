import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

import type { RunState } from "~/db/schema/enums";
import { repo } from "~/db/schema/repo";
import { workspace } from "~/db/schema/workspace";

// Plain current-state table for an agent — the first-class entity that the
// vestigial Python `Task` (models.py) becomes. The versioned
// TaskInputs/TaskState object_type-discriminated unions and the frozen-schema
// guard are dropped (RW-SIMP-3); their useful fields are flattened onto this
// row. `run_state` replaces the misleadingly-named `outcome`. The UI `status`
// is computed in the projection (Task 4.3), not stored. Multi-tenancy columns
// (organization_reference/user_reference) and max_seconds are dropped.
export const agent = sqliteTable("agent", {
  objectId: text("object_id").primaryKey(),
  createdAt: text("created_at")
    .notNull()
    .$defaultFn(() => new Date().toISOString()),
  projectId: text("project_id")
    .notNull()
    .references(() => repo.objectId),
  // Set once the agent has a workspace (AgentTaskStateV2.workspace_id).
  workspaceId: text("workspace_id").references(() => workspace.objectId),

  // From AgentTaskInputsV2 (the agent's launch config + starting state).
  agentConfig: text("agent_config", { mode: "json" }).$type<Record<string, unknown>>().notNull(),
  startingGitHash: text("starting_git_hash"),
  systemPrompt: text("system_prompt"),
  defaultModel: text("default_model"),

  // Run lifecycle.
  runState: text("run_state").$type<RunState>().notNull().default("QUEUED"),
  error: text("error", { mode: "json" }).$type<unknown>(),

  // From AgentTaskStateV2 (resume state).
  title: text("title"),
  lastProcessedMessageId: text("last_processed_message_id"),
  // Harness session ids used for --resume (Claude / Pi), populated by Task 5.4.
  claudeSessionId: text("claude_session_id"),
  piSessionId: text("pi_session_id"),
  // Terminal agents only.
  terminalSessionId: text("terminal_session_id"),
  terminalShellPid: integer("terminal_shell_pid"),
  // Pi agents only: the curated model catalog + current model.
  availableModels: text("available_models", { mode: "json" })
    .$type<unknown[]>()
    .notNull()
    .$defaultFn(() => []),
  currentModel: text("current_model", { mode: "json" }).$type<unknown>(),

  // User interaction.
  isDeleted: integer("is_deleted", { mode: "boolean" }).notNull().default(false),
  isDeleting: integer("is_deleting", { mode: "boolean" }).notNull().default(false),
  lastReadAt: text("last_read_at"),
}, (table) => [index("agent_workspace_id_idx").on(table.workspaceId)]);

export type AgentRow = typeof agent.$inferSelect;
export type NewAgentRow = typeof agent.$inferInsert;
