import { atom } from "jotai";

import type { AgentTypeName, TerminalAgentRegistration } from "~/api";

import { userConfigAtom } from "./userConfig";

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
  pi: "Pi",
  terminal: "Terminal Agent",
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

/** Resolve a stored agent type to the one that will actually be created, given
 * the live registrations: a `registered:<id>` whose registration no longer
 * exists falls back to Claude (the create path can't launch a deleted
 * registration). Shared by the create flow and the new-workspace form's
 * capability gate so "is this effectively Claude?" is one derivation and the
 * two surfaces cannot drift. */
export const resolveEffectiveAgentType = (
  stored: StoredAgentType,
  registrations: ReadonlyArray<TerminalAgentRegistration>,
): { agentType: AgentTypeName; registrationId: string | undefined } => {
  const { agentType, registrationId } = parseStoredAgentType(stored);
  const isMissingRegistration =
    agentType === "registered" && !registrations.some((r) => r.registrationId === registrationId);
  return isMissingRegistration ? { agentType: "claude", registrationId: undefined } : { agentType, registrationId };
};

/** The most-recently-used agent type, the default a plain `+` click (or a
 * bare `sculpt agent create`) creates.
 *
 * Read-only and backed by the server-side `UserConfig.lastUsedAgentType`, so
 * the app's "+" button and the sculpt CLI share one default. Defaults to
 * Claude when unset. Write through `useUserConfig().updateConfig({
 * lastUsedAgentType })`, which optimistically updates `userConfigAtom`. */
export const lastUsedAgentTypeAtom = atom<StoredAgentType>(
  (get) => (get(userConfigAtom)?.lastUsedAgentType as StoredAgentType | null) ?? "claude",
);
