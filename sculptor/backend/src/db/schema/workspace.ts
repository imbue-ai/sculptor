import { index, integer, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

import type { DiffStatus, WorkspaceInitializationStrategy } from "~/db/schema/enums";
import { repo } from "~/db/schema/repo";

// Plain current-state table for a workspace, mirroring Workspace in
// sculptor/sculptor/database/models.py. project_id FKs to repo.object_id (the
// `repo` table is serialized as `project` on the wire — see repo.ts). The
// multi-tenancy organization_reference column is dropped.
export const workspace = sqliteTable("workspace", {
  objectId: text("object_id").primaryKey(),
  createdAt: text("created_at")
    .notNull()
    .$defaultFn(() => new Date().toISOString()),
  projectId: text("project_id")
    .notNull()
    .references(() => repo.objectId),
  description: text("description").notNull(),
  initializationStrategy: text("initialization_strategy").$type<WorkspaceInitializationStrategy>().notNull(),
  sourceBranch: text("source_branch"),
  targetBranch: text("target_branch"),
  // Embedded in on-disk workspace paths; preserved verbatim for resume.
  environmentId: text("environment_id"),
  sourceGitHash: text("source_git_hash"),
  isDeleted: integer("is_deleted", { mode: "boolean" }).notNull().default(false),
  isOpen: integer("is_open", { mode: "boolean" }).notNull().default(true),
  setupCommandTriggered: integer("setup_command_triggered", { mode: "boolean" }).notNull().default(false),
  setupStatus: text("setup_status").notNull().default("pending"),
  setupRunId: text("setup_run_id"),
  setupCommand: text("setup_command"),
  setupExitCode: integer("setup_exit_code"),
  setupStartedAt: real("setup_started_at"),
  setupFinishedAt: real("setup_finished_at"),
  setupLogPath: text("setup_log_path"),
  setupLogTruncated: integer("setup_log_truncated", { mode: "boolean" }).notNull().default(false),
  diffStatus: text("diff_status").$type<DiffStatus>().notNull().default("NONE"),
  diffUpdatedAt: text("diff_updated_at"),
  requestedBranchName: text("requested_branch_name"),
}, (table) => [index("workspace_project_id_idx").on(table.projectId)]);

export type WorkspaceRow = typeof workspace.$inferSelect;
export type NewWorkspaceRow = typeof workspace.$inferInsert;
