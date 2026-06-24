import { desc, eq } from "drizzle-orm";

import type { Orm } from "~/db/orm";
import { type NewNotificationRow, notification, type NotificationRow } from "~/db/schema";

export function createNotification(orm: Orm, values: NewNotificationRow): NotificationRow {
  return orm.insert(notification).values(values).returning().get();
}

export function getNotification(orm: Orm, objectId: string): NotificationRow | undefined {
  return orm.select().from(notification).where(eq(notification.objectId, objectId)).get();
}

export function listNotifications(orm: Orm, limit = 100): NotificationRow[] {
  return orm.select().from(notification).orderBy(desc(notification.createdAt)).limit(limit).all();
}

export function deleteNotification(orm: Orm, objectId: string): void {
  orm.delete(notification).where(eq(notification.objectId, objectId)).run();
}
