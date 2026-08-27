import { skipToken, useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";
import { ModelCatalogState } from "../../../api";
import { taskQueryKey } from "../queryClient.ts";
export { useTask as useAgent } from "./useTask";

// Each hook subscribes to a single agent in the TanStack Query cache (fed by the
// WS bridge, `skipToken` so it never fetches — see useTask) and returns one
// derived field via `select`. TanStack's structural sharing keeps the selected
// value referentially stable across frames that don't touch it, so a subscriber
// re-renders only when ITS field changes — the fine-grained property the Jotai
// selector families used to provide. These hooks are the narrow accessors for
// `harnessCapabilities.<field>`: a mistyped capability key would read
// `undefined` and gate open, so every capability read goes through one here.

// Subscribe to a single agent, projecting one field through `pick`. The cache is
// subscription-only (`skipToken`), matching useTask; `pick` runs on every cached
// frame and its structurally-shared result gates re-renders. TanStack skips
// `select` entirely while the query has no data (the stream hasn't delivered the
// agent), so we coalesce that gap by evaluating `pick(null)` — the same value the
// old selector atoms yielded for an absent agent, since `agentAtomFamily` defaulted
// to `null`.
const useTaskField = <T>(taskId: string, pick: (task: CodingAgentTaskView | null) => T): T => {
  const { data } = useQuery<CodingAgentTaskView | null, unknown, T>({
    queryKey: taskQueryKey(taskId),
    queryFn: skipToken,
    select: pick,
  });
  return data === undefined ? pick(null) : data;
};

/** Subscribe to only the agent's status field. Re-renders only when status changes. */
export const useAgentStatusField = (taskId: string): TaskStatus | undefined =>
  useTaskField(taskId, (task) => task?.status);

/** Subscribe to only the agent's model field. Terminal agents carry no model
 * (`model` is null); treat that the same as "unknown". */
export const useAgentModel = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.model ?? undefined);

/** Subscribe to the workspace that owns the agent — immutable once the view has
 * loaded, so subscribers re-render only on load/removal, never on agent churn. */
export const useTaskWorkspaceId = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.workspaceId ?? undefined);

/** Subscribe to the harness's backend-sourced model catalog (pi): the fetched
 *  list (empty for Claude), or NOT_FETCHED_YET while the start-time probe runs. */
export const useAgentAvailableModels = (taskId: string): ReadonlyArray<ModelOption> | ModelCatalogState =>
  useTaskField(taskId, (task) => task?.availableModels ?? ModelCatalogState.NOT_FETCHED_YET);

/** Subscribe to the model_id the switcher should show selected for a backend list (pi). */
export const useAgentSelectedModelId = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.selectedModelId ?? undefined);

/** Subscribe to whether the harness sources its model catalog from a backend (pi). */
export const useAgentSourcesBackendModels = (taskId: string): boolean =>
  useTaskField(taskId, (task) => task?.sourcesBackendModels ?? false);

/** Subscribe to the Settings section the composer's "Go to harness configuration" CTA
 * opens when this harness has no usable model (harness-owned: pi -> Pi, else Dependencies). */
export const useTaskConfigurationSettingsSection = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.configurationSettingsSection);

export const useAgentIsAutoCompacting = (taskId: string): boolean =>
  useTaskField(taskId, (task) => task?.isAutoCompacting ?? false);

/** Subscribe to only the agent's `supports_interactive_backchannel` capability. */
export const useAgentSupportsInteractiveBackchannel = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsInteractiveBackchannel);

/** Subscribe to only the agent's `supports_fast_mode` capability. */
export const useAgentSupportsFastMode = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsFastMode);

/** Subscribe to only the agent's `supports_file_attachments` capability. */
export const useAgentSupportsFileAttachments = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsFileAttachments);

/** Subscribe to only the agent's `supports_image_input` capability. */
export const useAgentSupportsImageInput = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsImageInput);

/** Subscribe to only the agent's `supports_skills` capability. */
export const useAgentSupportsSkills = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsSkills);

/** Subscribe to only the agent's `supports_sub_agents` capability. */
export const useAgentSupportsSubAgents = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsSubAgents);

/** Subscribe to only the agent's `supports_interruption` capability. */
export const useAgentSupportsInterruption = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsInterruption);

/** Subscribe to only the agent's `supports_file_references` capability. */
export const useAgentSupportsFileReferences = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsFileReferences);

/** Subscribe to only the agent's `supports_context_reset` capability. */
export const useAgentSupportsContextReset = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsContextReset);

/** Subscribe to only the agent's `supports_compaction` capability. */
export const useAgentSupportsCompaction = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsCompaction);

/** Subscribe to only the agent's `supports_background_tasks` capability. */
export const useAgentSupportsBackgroundTasks = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsBackgroundTasks);

/** Subscribe to only the agent's `supports_session_resume` capability. */
export const useAgentSupportsSessionResume = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsSessionResume);

/** Subscribe to only the agent's `supports_tool_use_rendering` capability. */
export const useAgentSupportsToolUseRendering = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsToolUseRendering);

/** Subscribe to only the agent's `supports_chat_interface` capability —
 * the coarse main-panel switch (chat interface vs terminal panel). */
export const useAgentSupportsChatInterface = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsChatInterface);

/** Subscribe to only the agent's `supports_model_selection` capability. */
export const useAgentSupportsModelSelection = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsModelSelection);

/** Subscribe to only the agent's `accepts_automated_prompts` field — true
 * only for registered terminal agents whose registration opted in. */
export const useAgentAcceptsAutomatedPrompts = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.acceptsAutomatedPrompts);
