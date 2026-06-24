import { asc, eq } from "drizzle-orm";

import type { Orm } from "~/db/orm";
import { type NewRepoRow, repo, type RepoRow } from "~/db/schema";

// CRUD/query layer for `repo` (serialized as `project` on the wire — see
// schema/repo.ts). Plain current-state rows: a write is one INSERT/UPDATE.

export function createRepo(orm: Orm, values: NewRepoRow): RepoRow {
  return orm.insert(repo).values(values).returning().get();
}

export function getRepo(orm: Orm, objectId: string): RepoRow | undefined {
  return orm.select().from(repo).where(eq(repo.objectId, objectId)).get();
}

// Active = not soft-deleted, matching the Python default list semantics.
export function listActiveRepos(orm: Orm): RepoRow[] {
  return orm.select().from(repo).where(eq(repo.isDeleted, false)).orderBy(asc(repo.createdAt)).all();
}

export function updateRepo(orm: Orm, objectId: string, patch: Partial<NewRepoRow>): RepoRow | undefined {
  return orm.update(repo).set(patch).where(eq(repo.objectId, objectId)).returning().get();
}

export function softDeleteRepo(orm: Orm, objectId: string): void {
  orm.update(repo).set({ isDeleted: true }).where(eq(repo.objectId, objectId)).run();
}
