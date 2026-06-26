// Shared access helpers for the raw append-only agent-message log.
//
// The derived view walks the RAW agent-message dicts (`agent_message.message`)
// — the same `object_type`-discriminated shape the message fold consumes —
// rather than the folded ChatMessage[]. The
// Python `CodingAgentTaskView.status` / activity / task-list derivations walk
// `self._messages` (the raw Message objects); these helpers mirror that access.

export type RawMessage = Record<string, unknown>;

export function objectType(message: RawMessage): string {
  return message["object_type"] as string;
}
