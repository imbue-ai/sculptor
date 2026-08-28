import { skipToken, useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";
import { ModelCatalogState } from "../../../api";
import { agentQueryKey } from "../queryClient.ts";

// Each hook subscribes to a single agent in the TanStack Query cache (fed by the
// WS bridge, `skipToken` so it never fetches — see useAgent) and returns one
// derived field via `select`. TanStack's structural sharing keeps the selected
// value referentially stable across frames that don't touch it, so a subscriber
// re-renders only when ITS field changes — the fine-grained property the Jotai
// selector families used to provide. These hooks are the narrow accessors for
// `harnessCapabilities.<field>`: a mistyped capability key would read
// `undefined` and gate open, so every capability read goes through one here.

// Subscribe to a single agent, projecting one field through `pick`. The cache is
// subscription-only (`skipToken`), matching useAgent; `pick` runs on every cached
// frame and its structurally-shared result gates re-renders. TanStack skips
// `select` entirely while the query has no data (the stream hasn't delivered the
// agent), so we coalesce that gap by evaluating `pick(null)` — the same value the
// old selector atoms yielded for an absent agent, since `agentAtomFamily` defaulted
// to `null`.
const useAgentField = <T>(agentId: string, pick: (agent: CodingAgentTaskView | null) => T): T => {
  const { data } = useQuery<CodingAgentTaskView | null, unknown, T>({
    queryKey: agentQueryKey(agentId),
    queryFn: skipToken,
    select: pick,
  });
  return data === undefined ? pick(null) : data;
};

/** Subscribe to only the agent's status field. Re-renders only when status changes. */
export const useAgentStatusField = (agentId: string): TaskStatus | undefined =>
  useAgentField(agentId, (agent) => agent?.status);

/** Subscribe to only the agent's model field. Terminal agents carry no model
 * (`model` is null); treat that the same as "unknown". */
export const useAgentModel = (agentId: string): string | undefined =>
  useAgentField(agentId, (agent) => agent?.model ?? undefined);

/** Subscribe to the workspace that owns the agent — immutable once the view has
 * loaded, so subscribers re-render only on load/removal, never on agent churn. */
export const useAgentWorkspaceId = (agentId: string): string | undefined =>
  useAgentField(agentId, (agent) => agent?.workspaceId ?? undefined);

/** Subscribe to the harness's backend-sourced model catalog (pi): the fetched
 *  list (empty for Claude), or NOT_FETCHED_YET while the start-time probe runs. */
export const useAgentAvailableModels = (agentId: string): ReadonlyArray<ModelOption> | ModelCatalogState =>
  useAgentField(agentId, (agent) => agent?.availableModels ?? ModelCatalogState.NOT_FETCHED_YET);

/** Subscribe to the model_id the switcher should show selected for a backend list (pi). */
export const useAgentSelectedModelId = (agentId: string): string | undefined =>
  useAgentField(agentId, (agent) => agent?.selectedModelId ?? undefined);

/** Subscribe to whether the harness sources its model catalog from a backend (pi). */
export const useAgentSourcesBackendModels = (agentId: string): boolean =>
  useAgentField(agentId, (agent) => agent?.sourcesBackendModels ?? false);

/** Subscribe to the Settings section the composer's "Go to harness configuration" CTA
 * opens when this harness has no usable model (harness-owned: pi -> Pi, else Dependencies). */
export const useAgentConfigurationSettingsSection = (agentId: string): string | undefined =>
  useAgentField(agentId, (agent) => agent?.configurationSettingsSection);

export const useAgentIsAutoCompacting = (agentId: string): boolean =>
  useAgentField(agentId, (agent) => agent?.isAutoCompacting ?? false);

/** Subscribe to only the agent's `supports_interactive_backchannel` capability. */
export const useAgentSupportsInteractiveBackchannel = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsInteractiveBackchannel);

/** Subscribe to only the agent's `supports_fast_mode` capability. */
export const useAgentSupportsFastMode = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsFastMode);

/** Subscribe to only the agent's `supports_file_attachments` capability. */
export const useAgentSupportsFileAttachments = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsFileAttachments);

/** Subscribe to only the agent's `supports_image_input` capability. */
export const useAgentSupportsImageInput = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsImageInput);

/** Subscribe to only the agent's `supports_skills` capability. */
export const useAgentSupportsSkills = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsSkills);

/** Subscribe to only the agent's `supports_sub_agents` capability. */
export const useAgentSupportsSubAgents = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsSubAgents);

/** Subscribe to only the agent's `supports_interruption` capability. */
export const useAgentSupportsInterruption = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsInterruption);

/** Subscribe to only the agent's `supports_file_references` capability. */
export const useAgentSupportsFileReferences = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsFileReferences);

/** Subscribe to only the agent's `supports_context_reset` capability. */
export const useAgentSupportsContextReset = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsContextReset);

/** Subscribe to only the agent's `supports_compaction` capability. */
export const useAgentSupportsCompaction = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsCompaction);

/** Subscribe to only the agent's `supports_background_tasks` capability. */
export const useAgentSupportsBackgroundTasks = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsBackgroundTasks);

/** Subscribe to only the agent's `supports_session_resume` capability. */
export const useAgentSupportsSessionResume = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsSessionResume);

/** Subscribe to only the agent's `supports_tool_use_rendering` capability. */
export const useAgentSupportsToolUseRendering = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsToolUseRendering);

/** Subscribe to only the agent's `supports_chat_interface` capability —
 * the coarse main-panel switch (chat interface vs terminal panel). */
export const useAgentSupportsChatInterface = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsChatInterface);

/** Subscribe to only the agent's `supports_model_selection` capability. */
export const useAgentSupportsModelSelection = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.harnessCapabilities.supportsModelSelection);

/** Subscribe to only the agent's `accepts_automated_prompts` field — true
 * only for registered terminal agents whose registration opted in. */
export const useAgentAcceptsAutomatedPrompts = (agentId: string): boolean | undefined =>
  useAgentField(agentId, (agent) => agent?.acceptsAutomatedPrompts);
