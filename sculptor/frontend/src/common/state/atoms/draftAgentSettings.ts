import type { PrimitiveAtom } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";

import type { EffortLevel, LlmModel } from "../../../api";
import type { AgentID } from "../ids.ts";

/**
 * Per-agent fast-mode, effort, and model preference, persisted to localStorage
 * so it survives reloads, Electron relaunches after sleep, and hot-reloads.
 *
 * `null` means "not yet initialized for this agent" — the ChatInput mount
 * effect seeds the user's current default once `userConfig` is loaded.
 *
 * `getOnInit: true` reads the stored value synchronously when the atom is
 * first created. Without it, a freshly-mounted atom transiently reads its
 * `null` initial value until jotai's async hydration runs — and if ChatInput
 * mounts late (e.g. gated behind the `supports_chat_interface` capability
 * load), the seeding effect sees that spurious `null` after `userConfig` has
 * loaded and clobbers the persisted preference with the default. Hydrating on
 * init makes `null` mean "genuinely no stored value", so persistence survives
 * a reload regardless of when ChatInput mounts.
 */

const fastModeStorageKey = (agentId: AgentID): string => `sculptor-fast-mode-${agentId}`;
const effortStorageKey = (agentId: AgentID): string => `sculptor-effort-${agentId}`;
const modelStorageKey = (agentId: AgentID): string => `sculptor-model-${agentId}`;

export const fastModeAtomFamily = atomFamily<AgentID, PrimitiveAtom<boolean | null>>((agentId) =>
  atomWithStorage<boolean | null>(fastModeStorageKey(agentId), null, undefined, { getOnInit: true }),
);

export const effortAtomFamily = atomFamily<AgentID, PrimitiveAtom<EffortLevel | null>>((agentId) =>
  atomWithStorage<EffortLevel | null>(effortStorageKey(agentId), null, undefined, { getOnInit: true }),
);

export const modelAtomFamily = atomFamily<AgentID, PrimitiveAtom<LlmModel | null>>((agentId) =>
  atomWithStorage<LlmModel | null>(modelStorageKey(agentId), null, undefined, { getOnInit: true }),
);

/** Drop per-agent stored preferences when an agent is deleted. */
export const removeAgentSettings = (agentId: AgentID): void => {
  localStorage.removeItem(fastModeStorageKey(agentId));
  localStorage.removeItem(effortStorageKey(agentId));
  localStorage.removeItem(modelStorageKey(agentId));
  fastModeAtomFamily.remove(agentId);
  effortAtomFamily.remove(agentId);
  modelAtomFamily.remove(agentId);
};
