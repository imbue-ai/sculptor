import { atomWithStorage } from "jotai/utils";

import type { AgentTypeName } from "~/api";

export const agentTabOrderAtom = atomWithStorage<Record<string, Array<string>>>(
  "sculptor-agent-tab-order",
  {},
  undefined,
  { getOnInit: true },
);

/** The agent type a plain `+` click creates.
 *
 * Registered terminal agents are stored as `registered:<registrationId>` so
 * a plain click recreates the same registered agent. */
export type StoredAgentType = AgentTypeName | `registered:${string}`;

export const REGISTERED_AGENT_TYPE_PREFIX = "registered:";

/** Encode a registration id into the stored `registered:<id>` form. */
export const encodeRegisteredAgentType = (registrationId: string): StoredAgentType =>
  `${REGISTERED_AGENT_TYPE_PREFIX}${registrationId}`;

/** Split a stored agent type into the wire agent type and (for registered
 * agents) the registration id. */
export const parseStoredAgentType = (
  value: StoredAgentType,
): { agentType: AgentTypeName; registrationId: string | undefined } =>
  value.startsWith(REGISTERED_AGENT_TYPE_PREFIX)
    ? { agentType: "registered", registrationId: value.slice(REGISTERED_AGENT_TYPE_PREFIX.length) }
    : { agentType: value as AgentTypeName, registrationId: undefined };

export const lastUsedAgentTypeAtom = atomWithStorage<StoredAgentType>("lastUsedAgentType", "claude", undefined, {
  getOnInit: true,
});
