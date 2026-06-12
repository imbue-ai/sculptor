import { atomWithStorage } from "jotai/utils";

import type { AgentTypeName } from "~/api";

export const agentTabOrderAtom = atomWithStorage<Record<string, Array<string>>>(
  "sculptor-agent-tab-order",
  {},
  undefined,
  { getOnInit: true },
);

/** The agent type a plain `+` click creates (REQ-TYPE-6).
 *
 * Registered terminal agents are stored as `registered:<registrationId>` so
 * a plain click recreates the same registered agent. */
export type StoredAgentType = AgentTypeName | `registered:${string}`;

export const lastUsedAgentTypeAtom = atomWithStorage<StoredAgentType>("lastUsedAgentType", "claude", undefined, {
  getOnInit: true,
});
