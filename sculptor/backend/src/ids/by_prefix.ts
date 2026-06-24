import { findAgentsByPrefix } from "~/db/repositories/agents";
import type { Orm } from "~/db/orm";

// Errors mirroring the Python /api/v1/agents/by-prefix handler (web/app.py):
// no match -> 404, ambiguous -> 409. The HTTP layer (Phase 6) maps these to the
// status codes. There is no minimum prefix length (Python enforces none).
export class AgentPrefixNotFoundError extends Error {
  constructor(public readonly prefix: string) {
    super(`no agent matches prefix '${prefix}'`);
  }
}

export class AgentPrefixAmbiguousError extends Error {
  constructor(
    public readonly prefix: string,
    public readonly matches: string[],
  ) {
    super(`ambiguous prefix '${prefix}' matches ${matches.length} agents: ${matches.join(", ")}`);
  }
}

// Resolves a short prefix to a unique full agent id over non-deleted agents,
// accepting both tsk_ and agt_ prefixes. Throws AgentPrefixNotFoundError /
// AgentPrefixAmbiguousError to match Python's 404/409 behavior.
export function resolveAgentByPrefix(orm: Orm, prefix: string): string {
  const matches = findAgentsByPrefix(orm, prefix).map((row) => row.objectId);
  if (matches.length === 0) {
    throw new AgentPrefixNotFoundError(prefix);
  }
  if (matches.length > 1) {
    throw new AgentPrefixAmbiguousError(prefix, matches);
  }
  return matches[0]!;
}
