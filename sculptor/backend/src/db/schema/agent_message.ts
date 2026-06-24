import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

import { agent } from "~/db/schema/agent";
import type { AgentMessageSource } from "~/db/schema/enums";

// Append-only message log, mirroring SavedAgentMessage in
// sculptor/sculptor/database/models.py. This is the primary place the product
// exposes full history (RW-DATA-7); rows are NEVER mutated — the projection
// (Phase 4) folds them. object_id is the message's own id (= message.message_id);
// the writer (Task 2.4) enforces the object_id/source/is_partial invariants the
// Python model_post_init checked. task_id is renamed agent_id.
export const agentMessage = sqliteTable("agent_message", {
  objectId: text("object_id").primaryKey(),
  createdAt: text("created_at")
    .notNull()
    .$defaultFn(() => new Date().toISOString()),
  agentId: text("agent_id")
    .notNull()
    .references(() => agent.objectId),
  message: text("message", { mode: "json" }).$type<Record<string, unknown>>().notNull(),
  source: text("source").$type<AgentMessageSource>().notNull(),
  isPartial: integer("is_partial", { mode: "boolean" }).notNull(),
}, (table) => [index("agent_message_agent_id_idx").on(table.agentId)]);

export type AgentMessageRow = typeof agentMessage.$inferSelect;
export type NewAgentMessageRow = typeof agentMessage.$inferInsert;
