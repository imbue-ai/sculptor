import { eq } from "drizzle-orm";

import type { Orm } from "~/db/orm";
import { userSettings, type UserSettingsRow } from "~/db/schema";

// The DB carries only the local user identity; the real config lives in
// config.toml (Task 1.5). There is a single local user, so these read/upsert
// the one row.

export function getUserSettings(orm: Orm): UserSettingsRow | undefined {
  return orm.select().from(userSettings).get();
}

export function ensureUserSettings(orm: Orm, objectId: string): UserSettingsRow {
  const existing = orm.select().from(userSettings).where(eq(userSettings.objectId, objectId)).get();
  if (existing !== undefined) {
    return existing;
  }
  return orm.insert(userSettings).values({ objectId }).returning().get();
}
