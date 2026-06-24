import { sqliteTable, text } from "drizzle-orm/sqlite-core";

import { agent } from "~/db/schema/agent";
import type { NotificationImportance } from "~/db/schema/enums";
import { repo } from "~/db/schema/repo";

// Plain current-state table for a notification, mirroring Notification in
// sculptor/sculptor/database/models.py. task_id is renamed agent_id; the
// multi-tenancy user_reference column is dropped. A notification can target a
// specific agent, a whole project (repo), or neither.
export const notification = sqliteTable("notification", {
  objectId: text("object_id").primaryKey(),
  createdAt: text("created_at")
    .notNull()
    .$defaultFn(() => new Date().toISOString()),
  message: text("message").notNull(),
  importance: text("importance").$type<NotificationImportance>().notNull().default("ACTIVE"),
  agentId: text("agent_id").references(() => agent.objectId),
  projectId: text("project_id").references(() => repo.objectId),
});

export type NotificationRow = typeof notification.$inferSelect;
export type NewNotificationRow = typeof notification.$inferInsert;
