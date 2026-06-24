import { and, desc, eq, inArray } from "drizzle-orm";

import type { Orm } from "~/db/orm";
import type { RunState } from "~/db/schema";
import { agent, type AgentRow, type NewAgentRow } from "~/db/schema";

// Non-deleted agents that are not in a terminal run state (QUEUED/RUNNING) —
// the set the runner re-supervises on startup (Task 5.1, RW-DATA-6).
const NON_TERMINAL_RUN_STATES: RunState[] = ["QUEUED", "RUNNING"];

export function listNonTerminalAgents(orm: Orm): AgentRow[] {
  return orm
    .select()
    .from(agent)
    .where(and(eq(agent.isDeleted, false), inArray(agent.runState, NON_TERMINAL_RUN_STATES)))
    .all();
}

export function createAgent(orm: Orm, values: NewAgentRow): AgentRow {
  return orm.insert(agent).values(values).returning().get();
}

export function getAgent(orm: Orm, objectId: string): AgentRow | undefined {
  return orm.select().from(agent).where(eq(agent.objectId, objectId)).get();
}

// Non-deleted agents whose id starts with the prefix. Filtered in JS (not via
// SQL LIKE) because typeids contain `_`, which is a LIKE single-char wildcard;
// this matches the Python str(object_id).startswith(prefix) semantics exactly.
export function findAgentsByPrefix(orm: Orm, prefix: string): AgentRow[] {
  return orm
    .select()
    .from(agent)
    .where(eq(agent.isDeleted, false))
    .all()
    .filter((row) => row.objectId.startsWith(prefix));
}

// Resolves a full id, or a unique short prefix when no exact row exists.
// Accepts both tsk_ and agt_ ids transparently (the prefix is just part of the
// string). Returns undefined for no match or an ambiguous prefix.
export function getAgentByIdOrPrefix(orm: Orm, idOrPrefix: string): AgentRow | undefined {
  const exact = getAgent(orm, idOrPrefix);
  if (exact !== undefined) {
    return exact;
  }
  const matches = findAgentsByPrefix(orm, idOrPrefix);
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
