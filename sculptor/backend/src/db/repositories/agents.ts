import { and, desc, eq, like } from "drizzle-orm";

import type { Orm } from "~/db/orm";
import type { RunState } from "~/db/schema";
import { agent, type AgentRow, type NewAgentRow } from "~/db/schema";

export function createAgent(orm: Orm, values: NewAgentRow): AgentRow {
  return orm.insert(agent).values(values).returning().get();
}

export function getAgent(orm: Orm, objectId: string): AgentRow | undefined {
  return orm.select().from(agent).where(eq(agent.objectId, objectId)).get();
}

// Resolves a full id, or a unique short prefix when no exact row exists. The
// dual-prefix (tsk_/agt_) handling is finalized in Task 2.5; this provides the
// prefix lookup it builds on. Returns undefined for no match or an ambiguous
// prefix.
export function getAgentByIdOrPrefix(orm: Orm, idOrPrefix: string): AgentRow | undefined {
  const exact = getAgent(orm, idOrPrefix);
  if (exact !== undefined) {
    return exact;
  }
  const matches = orm
    .select()
    .from(agent)
    .where(like(agent.objectId, `${idOrPrefix}%`))
    .limit(2)
    .all();
  return matches.length === 1 ? matches[0] : undefined;
}

export function listAgentsByWorkspace(orm: Orm, workspaceId: string): AgentRow[] {
  return orm
    .select()
    .from(agent)
    .where(and(eq(agent.workspaceId, workspaceId), eq(agent.isDeleted, false)))
    .orderBy(desc(agent.createdAt))
    .all();
}

export function updateAgent(orm: Orm, objectId: string, patch: Partial<NewAgentRow>): AgentRow | undefined {
  return orm.update(agent).set(patch).where(eq(agent.objectId, objectId)).returning().get();
}

export function setAgentRunState(orm: Orm, objectId: string, runState: RunState): void {
  orm.update(agent).set({ runState }).where(eq(agent.objectId, objectId)).run();
}

export function markAgentRead(orm: Orm, objectId: string): void {
  orm.update(agent).set({ lastReadAt: new Date().toISOString() }).where(eq(agent.objectId, objectId)).run();
}

export function softDeleteAgent(orm: Orm, objectId: string): void {
  orm.update(agent).set({ isDeleted: true }).where(eq(agent.objectId, objectId)).run();
}

export function setAgentDeleting(orm: Orm, objectId: string, isDeleting: boolean): void {
  orm.update(agent).set({ isDeleting }).where(eq(agent.objectId, objectId)).run();
}
