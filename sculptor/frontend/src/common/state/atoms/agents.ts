import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { CodingAgentTaskView, TaskStatus } from "../../../api";

// The agent atoms are legacy read models: the TanStack Query cache is the
// written store for agent state, and useTaskQueryMirror projects it into these
// atoms for the remaining Jotai readers. Nothing else should write them.
//
// React components read per-agent fields through the `useAgent*` hooks in
// `hooks/useAgentHelpers.ts` (select-based reads of the query cache). The
// selector families that survive here exist ONLY for atom-graph readers that
// derive from them inside Jotai `get(...)` — `workspaceAgentActions.ts` and
// `mentionDetails.ts`. When those derivations move off Jotai, these go too.

export const agentAtomFamily = atomFamily<string, PrimitiveAtom<CodingAgentTaskView | null>>(() =>
  atom<CodingAgentTaskView | null>(null),
);

export const agentIdsAtom = atom<ReadonlyArray<string> | undefined>(undefined);

export const agentsArrayAtom = atom<ReadonlyArray<CodingAgentTaskView> | undefined>((get) => {
  const agentIds = get(agentIdsAtom);
  if (agentIds === undefined) {
    return undefined;
  }
  return agentIds
    .map((id) => get(agentAtomFamily(id)))
    .filter((agent): agent is CodingAgentTaskView => agent !== null && !agent.isDeleted);
});

// Fine-grained derived atoms for agent fields still read inside Jotai atom
// graphs. Components subscribing to these only re-render when the specific
// field changes. Jotai uses Object.is for primitive comparisons, so string/
// boolean fields that stay the same across an agent object update will not
// notify subscribers.

export const agentStatusAtomFamily = atomFamily<string, Atom<TaskStatus | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.status),
);

// Terminal agents carry no model (`model` is null); treat that the same as "unknown".
export const agentModelAtomFamily = atomFamily<string, Atom<string | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.model ?? undefined),
);

export const agentSupportsChatInterfaceAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsChatInterface),
);

export const agentAcceptsAutomatedPromptsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.acceptsAutomatedPrompts),
);
