import type { Atom, PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";
import { isEqual } from "lodash";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";
import { removeAgentSettings } from "./draftAgentSettings.ts";

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

export const updateAgentsAtom = atom(null, (get, set, updates: Record<string, CodingAgentTaskView>) => {
  const seenIds = new Set(get(agentIdsAtom));
  let didIdsChange = false;

  Object.entries(updates).forEach(([id, agent]) => {
    if (agent.isDeleted) {
      if (seenIds.has(id)) {
        seenIds.delete(id);
        didIdsChange = true;
      }
      set(agentAtomFamily(id), null);
      removeAgentSettings(id);
      return;
    }

    // Skip atom update when the agent data hasn't changed to avoid unnecessary re-renders.
    const current = get(agentAtomFamily(id));
    if (!isEqual(current, agent)) {
      set(agentAtomFamily(id), agent);
    }

    if (!seenIds.has(id)) {
      seenIds.add(id);
      didIdsChange = true;
    }
  });

  // Write even when nothing changed if the list is still undefined: every
  // stream frame carries a task-view map, so the first one — empty in a
  // zero-agent instance — marks the list as loaded. Consumers rely on the
  // undefined → array transition to tell "still loading" from "no agents"
  // (e.g. WorkspacePage's agentless-workspace gate).
  if (didIdsChange || get(agentIdsAtom) === undefined) {
    set(agentIdsAtom, Array.from(seenIds));
  }
});

export const optimisticDeleteAgentAtom = atom(null, (get, set, agentId: string): CodingAgentTaskView | null => {
  const agent = get(agentAtomFamily(agentId));
  if (agent === null) {
    return null;
  }
  const snapshot = agent;
  set(agentAtomFamily(agentId), null);
  const currentIds = get(agentIdsAtom) ?? [];
  set(
    agentIdsAtom,
    currentIds.filter((id) => id !== agentId),
  );
  return snapshot;
});

export const rollbackDeleteAgentAtom = atom(
  null,
  (get, set, { agentId, snapshot }: { agentId: string; snapshot: CodingAgentTaskView }): void => {
    set(agentAtomFamily(agentId), snapshot);
    const currentIds = get(agentIdsAtom) ?? [];
    if (!currentIds.includes(agentId)) {
      set(agentIdsAtom, [...currentIds, agentId]);
    }
  },
);

// Fine-grained derived atoms for commonly-read agent fields.
// Components subscribing to these only re-render when the specific field changes.
// Jotai uses Object.is for primitive comparisons, so string/boolean fields that
// stay the same across an agent object update will not notify subscribers.

export const agentStatusAtomFamily = atomFamily<string, Atom<TaskStatus | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.status),
);

// Terminal agents carry no model (`model` is null); treat that the same as "unknown".
export const agentModelAtomFamily = atomFamily<string, Atom<string | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.model ?? undefined),
);

// The workspace that owns the agent — immutable once the agent view has loaded,
// so subscribers re-render only on load/removal, never on agent churn (status,
// timestamps, artifacts, ...).
export const agentWorkspaceIdAtomFamily = atomFamily<string, Atom<string | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.workspaceId ?? undefined),
);

// A stable reference for the "no backend list" case, so the derived atom below
// keeps one identity across unrelated agent updates instead of a fresh array each
// recompute.
const EMPTY_MODEL_OPTIONS: ReadonlyArray<ModelOption> = [];

// The harness's backend-sourced model catalog (pi). A non-capability view field,
// so the no-direct-harness-capability-read ratchet does not apply. Empty for
// harnesses that source no list (Claude) — the switcher then falls back to its
// built-in PRODUCTION_MODELS.
export const agentAvailableModelsAtomFamily = atomFamily<string, Atom<ReadonlyArray<ModelOption>>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.availableModels ?? EMPTY_MODEL_OPTIONS),
);

// The model_id the switcher should show as selected for a backend-sourced list
// (pi), or undefined when the harness tracks no per-agent selection.
export const agentSelectedModelIdAtomFamily = atomFamily<string, Atom<string | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.selectedModelId ?? undefined),
);

// Whether the harness sources its switcher catalog from a backend (pi). A
// non-capability view field, so the no-direct-harness-capability-read ratchet
// does not apply.
export const agentSourcesBackendModelsAtomFamily = atomFamily<string, Atom<boolean>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.sourcesBackendModels ?? false),
);

export const agentIsAutoCompactingAtomFamily = atomFamily<string, Atom<boolean>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.isAutoCompacting ?? false),
);

export const agentSupportsInteractiveBackchannelAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsInteractiveBackchannel),
);

export const agentSupportsFastModeAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsFastMode),
);

export const agentSupportsFileAttachmentsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsFileAttachments),
);

export const agentSupportsImageInputAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsImageInput),
);

export const agentSupportsSkillsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsSkills),
);

export const agentSupportsSubAgentsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsSubAgents),
);

export const agentSupportsInterruptionAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsInterruption),
);

export const agentSupportsFileReferencesAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsFileReferences),
);

export const agentSupportsContextResetAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsContextReset),
);

export const agentSupportsCompactionAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsCompaction),
);

export const agentSupportsBackgroundTasksAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsBackgroundTasks),
);

export const agentSupportsSessionResumeAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsSessionResume),
);

export const agentSupportsToolUseRenderingAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsToolUseRendering),
);

export const agentSupportsChatInterfaceAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsChatInterface),
);

export const agentSupportsModelSelectionAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.harnessCapabilities.supportsModelSelection),
);

export const agentAcceptsAutomatedPromptsAtomFamily = atomFamily<string, Atom<boolean | undefined>>((agentId) =>
  atom((get) => get(agentAtomFamily(agentId))?.acceptsAutomatedPrompts),
);
