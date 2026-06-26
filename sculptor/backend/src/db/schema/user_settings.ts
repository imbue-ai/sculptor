import { sqliteTable, text } from "drizzle-orm/sqlite-core";

// Plain current-state table for the locally stored user, mirroring UserSettings
// in sculptor/sculptor/database/models.py — which holds essentially nothing.
// The real user config (account, telemetry-consent flags, agent defaults) lives
// in config.toml via UserConfig, NOT in the DB, and the one-time migration
// preserves config.toml untouched. The multi-tenancy user_reference column is
// dropped (local-first single-user).
export const userSettings = sqliteTable("user_settings", {
  objectId: text("object_id").primaryKey(),
  createdAt: text("created_at")
    .notNull()
    .$defaultFn(() => new Date().toISOString()),
});

export type UserSettingsRow = typeof userSettings.$inferSelect;
export type NewUserSettingsRow = typeof userSettings.$inferInsert;
