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

/** Display labels for the built-in agent types, shared by every picker (the
 * tab bar's + menu, the new-workspace select) so the surfaces can't drift.
 * Registered terminal agents label from their registration's display name. */
export const AGENT_TYPE_LABELS: Record<Exclude<AgentTypeName, "registered">, string> = {
  claude: "Claude",
  pi: "pi",
  terminal: "Terminal",
};

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

/** Minimal registration shape needed to label a registered agent. */
export type AgentRegistrationLabel = { registrationId: string; displayName: string };

/** Display label for a stored agent type — "Claude"/"pi" for the built-ins, or
 * the registration's display name for a registered agent (falls back to
 * "agent" if the registration is gone). Shared by the "New {type} agent" rows
 * in the panel palette and the empty-section quick add. */
export const agentTypeDisplayLabel = (
  stored: StoredAgentType,
  registrations: ReadonlyArray<AgentRegistrationLabel>,
): string => {
  const { agentType, registrationId } = parseStoredAgentType(stored);
  if (agentType === "registered") {
    return registrations.find((r) => r.registrationId === registrationId)?.displayName ?? "agent";
  }
  return AGENT_TYPE_LABELS[agentType as Exclude<AgentTypeName, "registered">];
};

export const lastUsedAgentTypeAtom = atomWithStorage<StoredAgentType>("lastUsedAgentType", "claude", undefined, {
  getOnInit: true,
});
