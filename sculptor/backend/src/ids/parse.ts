import { fromString, getType } from "typeid-js";

import { type AgentId, AGENT_ID_PREFIXES } from "~/ids/types";

// Raised when a value is not a valid typeid or carries the wrong prefix,
// mirroring the Python TypeIDPrefixMismatchError.
export class TypeIdPrefixMismatchError extends Error {}

function typeOf(value: string): string {
  // fromString throws on a malformed typeid (bad suffix/format).
  return getType(fromString(value));
}

// Validates that `value` is a typeid with the given prefix; returns it
// unchanged. Throws TypeIdPrefixMismatchError on a malformed id or a prefix
// mismatch.
export function parseId(prefix: string, value: string): string {
  let actual: string;
  try {
    actual = typeOf(value);
  } catch {
    throw new TypeIdPrefixMismatchError(`Invalid typeid '${value}'`);
  }
  if (actual !== prefix) {
    throw new TypeIdPrefixMismatchError(`Expected prefix '${prefix}', got '${actual}'`);
  }
  return value;
}

// Accepts BOTH `agt_…` and `tsk_…` as the same logical agent type.
export function parseAgentId(value: string): AgentId {
  let actual: string;
  try {
    actual = typeOf(value);
  } catch {
    throw new TypeIdPrefixMismatchError(`Invalid typeid '${value}'`);
  }
  if (!(AGENT_ID_PREFIXES as readonly string[]).includes(actual)) {
    throw new TypeIdPrefixMismatchError(`Expected an agent prefix (${AGENT_ID_PREFIXES.join("/")}), got '${actual}'`);
  }
  return value as AgentId;
}

export function isAgentId(value: string): boolean {
  try {
    parseAgentId(value);
    return true;
  } catch {
    return false;
  }
}
