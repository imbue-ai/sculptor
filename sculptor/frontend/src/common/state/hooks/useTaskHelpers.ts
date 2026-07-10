import { skipToken, useQuery } from "@tanstack/react-query";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";
import { ModelCatalogState } from "../../../api";
import { taskQueryKey } from "../../queryClient.ts";
export { useTask } from "./useTask";

// Each hook subscribes to a single task in the TanStack Query cache (fed by the
// WS bridge, `skipToken` so it never fetches — see useTask) and returns one
// derived field via `select`. TanStack's structural sharing keeps the selected
// value referentially stable across frames that don't touch it, so a subscriber
// re-renders only when ITS field changes — the fine-grained property the Jotai
// selector families used to provide. These hooks are the narrow accessors for
// `harnessCapabilities.<field>`: a mistyped capability key would read
// `undefined` and gate open, so every capability read goes through one here.

// Subscribe to a single task, projecting one field through `pick`. The cache is
// subscription-only (`skipToken`), matching useTask; `pick` runs on every cached
// frame and its structurally-shared result gates re-renders. TanStack skips
// `select` entirely while the query has no data (the stream hasn't delivered the
// task), so we coalesce that gap by evaluating `pick(null)` — the same value the
// old selector atoms yielded for an absent task, since `taskAtomFamily` defaulted
// to `null`.
const useTaskField = <T>(taskId: string, pick: (task: CodingAgentTaskView | null) => T): T => {
  const { data } = useQuery<CodingAgentTaskView | null, unknown, T>({
    queryKey: taskQueryKey(taskId),
    queryFn: skipToken,
    select: pick,
  });
  return data === undefined ? pick(null) : data;
};

/** Subscribe to only the task's status field. Re-renders only when status changes. */
export const useTaskStatus = (taskId: string): TaskStatus | undefined => useTaskField(taskId, (task) => task?.status);

/** Subscribe to only the task's model field. Terminal agents carry no model
 * (`model` is null); treat that the same as "unknown". */
export const useTaskModel = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.model ?? undefined);

/** Subscribe to the workspace that owns the task — immutable once the view has
 * loaded, so subscribers re-render only on load/removal, never on task churn. */
export const useTaskWorkspaceId = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.workspaceId ?? undefined);

/** Subscribe to the harness's backend-sourced model catalog (pi): the fetched
 *  list (empty for Claude), or NOT_FETCHED_YET while the start-time probe runs. */
export const useTaskAvailableModels = (taskId: string): ReadonlyArray<ModelOption> | ModelCatalogState =>
  useTaskField(taskId, (task) => task?.availableModels ?? ModelCatalogState.NOT_FETCHED_YET);

/** Subscribe to the model_id the switcher should show selected for a backend list (pi). */
export const useTaskSelectedModelId = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.selectedModelId ?? undefined);

/** Subscribe to whether the harness sources its model catalog from a backend (pi). */
export const useTaskSourcesBackendModels = (taskId: string): boolean =>
  useTaskField(taskId, (task) => task?.sourcesBackendModels ?? false);

/** Subscribe to the Settings section the composer's "Go to harness configuration" CTA
 * opens when this harness has no usable model (harness-owned: pi -> Pi, else Dependencies). */
export const useTaskConfigurationSettingsSection = (taskId: string): string | undefined =>
  useTaskField(taskId, (task) => task?.configurationSettingsSection);

export const useTaskIsAutoCompacting = (taskId: string): boolean =>
  useTaskField(taskId, (task) => task?.isAutoCompacting ?? false);

/** Subscribe to only the task's `supports_interactive_backchannel` capability. */
export const useTaskSupportsInteractiveBackchannel = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsInteractiveBackchannel);

/** Subscribe to only the task's `supports_fast_mode` capability. */
export const useTaskSupportsFastMode = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsFastMode);

/** Subscribe to only the task's `supports_file_attachments` capability. */
export const useTaskSupportsFileAttachments = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsFileAttachments);

/** Subscribe to only the task's `supports_image_input` capability. */
export const useTaskSupportsImageInput = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsImageInput);

/** Subscribe to only the task's `supports_skills` capability. */
export const useTaskSupportsSkills = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsSkills);

/** Subscribe to only the task's `supports_sub_agents` capability. */
export const useTaskSupportsSubAgents = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsSubAgents);

/** Subscribe to only the task's `supports_interruption` capability. */
export const useTaskSupportsInterruption = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsInterruption);

/** Subscribe to only the task's `supports_file_references` capability. */
export const useTaskSupportsFileReferences = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsFileReferences);

/** Subscribe to only the task's `supports_context_reset` capability. */
export const useTaskSupportsContextReset = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsContextReset);

/** Subscribe to only the task's `supports_compaction` capability. */
export const useTaskSupportsCompaction = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsCompaction);

/** Subscribe to only the task's `supports_background_tasks` capability. */
export const useTaskSupportsBackgroundTasks = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsBackgroundTasks);

/** Subscribe to only the task's `supports_session_resume` capability. */
export const useTaskSupportsSessionResume = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsSessionResume);

/** Subscribe to only the task's `supports_tool_use_rendering` capability. */
export const useTaskSupportsToolUseRendering = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsToolUseRendering);

/** Subscribe to only the task's `supports_chat_interface` capability —
 * the coarse main-panel switch (chat interface vs terminal panel). */
export const useTaskSupportsChatInterface = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsChatInterface);

/** Subscribe to only the task's `supports_model_selection` capability. */
export const useTaskSupportsModelSelection = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.harnessCapabilities.supportsModelSelection);

/** Subscribe to only the task's `accepts_automated_prompts` field — true
 * only for registered terminal agents whose registration opted in. */
export const useTaskAcceptsAutomatedPrompts = (taskId: string): boolean | undefined =>
  useTaskField(taskId, (task) => task?.acceptsAutomatedPrompts);
