import { and, asc, eq } from "drizzle-orm";
import { z } from "zod";

import type { Orm } from "~/db/orm";
import { agentMessage, type AgentMessageRow, agentMessageSourceSchema } from "~/db/schema";

// A message is "partial" iff it is a streaming response chunk, mirroring the
// Python isinstance(message, PartialResponseBlockAgentMessage) check.
const PARTIAL_MESSAGE_OBJECT_TYPE = "PartialResponseBlockAgentMessage";

export function isPartialMessage(message: Record<string, unknown>): boolean {
  return message.object_type === PARTIAL_MESSAGE_OBJECT_TYPE;
}

// The minimal message envelope the append invariants require. The full message
// payload is stored verbatim as JSON; only these fields are read here.
const messageEnvelopeSchema = z.object({
  message_id: z.string().min(1),
  source: agentMessageSourceSchema,
  object_type: z.string().min(1),
});

export interface ListByAgentOptions {
  includePartial?: boolean;
  limit?: number;
  offset?: number;
}

// Append-only writer. Derives object_id/source/is_partial from the message
// itself (porting SavedAgentMessage.build + model_post_init), so the row can
// never disagree with its payload; a malformed message (missing message_id,
// unknown source) is rejected.
export function appendAgentMessage(orm: Orm, agentId: string, message: Record<string, unknown>): AgentMessageRow {
  const envelope = messageEnvelopeSchema.parse(message);
  return orm
    .insert(agentMessage)
    .values({
      objectId: envelope.message_id,
      agentId,
      message,
      source: envelope.source,
      isPartial: envelope.object_type === PARTIAL_MESSAGE_OBJECT_TYPE,
    })
    .returning()
    .get();
}

export function getAgentMessage(orm: Orm, objectId: string): AgentMessageRow | undefined {
  return orm.select().from(agentMessage).where(eq(agentMessage.objectId, objectId)).get();
}

export function listAgentMessages(orm: Orm, agentId: string, options: ListByAgentOptions = {}): AgentMessageRow[] {
  const condition =
    options.includePartial === true
      ? eq(agentMessage.agentId, agentId)
      : and(eq(agentMessage.agentId, agentId), eq(agentMessage.isPartial, false));
  let query = orm.select().from(agentMessage).where(condition).orderBy(asc(agentMessage.createdAt)).$dynamic();
  if (options.limit !== undefined) {
    query = query.limit(options.limit);
  }
  if (options.offset !== undefined) {
    query = query.offset(options.offset);
  }
  return query.all();
}

// The single message-delete endpoint is the one exception to append-only; it
// must be explicit (the log is otherwise never mutated).
export function deleteAgentMessage(orm: Orm, objectId: string): void {
  orm.delete(agentMessage).where(eq(agentMessage.objectId, objectId)).run();
}
