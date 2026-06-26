import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

// Plain current-state table for a repository, mirroring Project in
// sculptor/sculptor/database/models.py. INTERNAL→WIRE NAME MAPPING: the table
// is named `repo` internally, but the HTTP/WebSocket API still serializes it as
// `project` / `project_id` (the frontend depends on this). The API layer owns
// that mapping. The multi-tenancy organization_reference column is dropped
// (local-first single-user).
export const repo = sqliteTable("repo", {
  objectId: text("object_id").primaryKey(),
  createdAt: text("created_at")
    .notNull()
    .$defaultFn(() => new Date().toISOString()),
  name: text("name").notNull(),
  // A file:// URL to the user's git repo. Copied verbatim by the migration so
  // workspace paths stay valid — do NOT normalize it.
  userGitRepoUrl: text("user_git_repo_url"),
  isPathAccessible: integer("is_path_accessible", { mode: "boolean" }).notNull().default(true),
  isDeleted: integer("is_deleted", { mode: "boolean" }).notNull().default(false),
  defaultSystemPrompt: text("default_system_prompt"),
  workspaceSetupCommand: text("workspace_setup_command"),
  namingPattern: text("naming_pattern"),
});

export type RepoRow = typeof repo.$inferSelect;
export type NewRepoRow = typeof repo.$inferInsert;
