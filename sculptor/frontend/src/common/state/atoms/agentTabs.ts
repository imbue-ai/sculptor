import { atomWithStorage } from "jotai/utils";

import type { AgentTypeName } from "~/api";

export const agentTabOrderAtom = atomWithStorage<Record<string, Array<string>>>(
  "sculptor-agent-tab-order",
  {},
  undefined,
  { getOnInit: true },
);

/** The agent type a plain `+` click creates (REQ-TYPE-6). */
export const lastUsedAgentTypeAtom = atomWithStorage<AgentTypeName>("lastUsedAgentType", "claude", undefined, {
  getOnInit: true,
});
