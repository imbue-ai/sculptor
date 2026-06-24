import { and, desc, eq } from "drizzle-orm";

import type { Orm } from "~/db/orm";
import type { DiffStatus } from "~/db/schema";
import { type NewWorkspaceRow, workspace, type WorkspaceRow } from "~/db/schema";

export function createWorkspace(orm: Orm, values: NewWorkspaceRow): WorkspaceRow {
  return orm.insert(workspace).values(values).returning().get();
}

export function getWorkspace(orm: Orm, objectId: string): WorkspaceRow | undefined {
  return orm.select().from(workspace).where(eq(workspace.objectId, objectId)).get();
}

export function listWorkspacesByRepo(orm: Orm, projectId: string): WorkspaceRow[] {
  return orm
    .select()
    .from(workspace)
    .where(and(eq(workspace.projectId, projectId), eq(workspace.isDeleted, false)))
    .orderBy(desc(workspace.createdAt))
    .all();
}

export function listRecentWorkspaces(orm: Orm, limit = 50): WorkspaceRow[] {
  return orm
    .select()
    .from(workspace)
    .where(eq(workspace.isDeleted, false))
    .orderBy(desc(workspace.createdAt))
    .limit(limit)
    .all();
}

export function updateWorkspace(orm: Orm, objectId: string, patch: Partial<NewWorkspaceRow>): WorkspaceRow | undefined {
  return orm.update(workspace).set(patch).where(eq(workspace.objectId, objectId)).returning().get();
}

export function setWorkspaceOpen(orm: Orm, objectId: string, isOpen: boolean): void {
  orm.update(workspace).set({ isOpen }).where(eq(workspace.objectId, objectId)).run();
}

export function setWorkspaceDiffStatus(orm: Orm, objectId: string, diffStatus: DiffStatus): void {
  orm
    .update(workspace)
    .set({ diffStatus, diffUpdatedAt: new Date().toISOString() })
    .where(eq(workspace.objectId, objectId))
    .run();
}

export function softDeleteWorkspace(orm: Orm, objectId: string): void {
  orm.update(workspace).set({ isDeleted: true }).where(eq(workspace.objectId, objectId)).run();
}
