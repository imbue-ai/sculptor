import { useAtomValue } from "jotai";

import type { ModelOption, TaskStatus } from "../../../api";
import {
  taskAcceptsAutomatedPromptsAtomFamily,
  taskAvailableModelsAtomFamily,
  taskIsAutoCompactingAtomFamily,
  taskModelAtomFamily,
  taskSelectedModelIdAtomFamily,
  taskSourcesBackendModelsAtomFamily,
  taskStatusAtomFamily,
  taskSupportsBackgroundTasksAtomFamily,
  taskSupportsChatInterfaceAtomFamily,
  taskSupportsCompactionAtomFamily,
  taskSupportsContextResetAtomFamily,
  taskSupportsFastModeAtomFamily,
  taskSupportsFileAttachmentsAtomFamily,
  taskSupportsFileReferencesAtomFamily,
  taskSupportsImageInputAtomFamily,
  taskSupportsInteractiveBackchannelAtomFamily,
  taskSupportsInterruptionAtomFamily,
  taskSupportsModelSelectionAtomFamily,
  taskSupportsSessionResumeAtomFamily,
  taskSupportsSkillsAtomFamily,
  taskSupportsSubAgentsAtomFamily,
  taskSupportsToolUseRenderingAtomFamily,
} from "../atoms/tasks";
import { useTask as useTaskFromCache } from "./useTask";

export const useTask = useTaskFromCache;

/** Subscribe to only the task's status field. Re-renders only when status changes. */
export const useTaskStatus = (taskId: string): TaskStatus | undefined => useAtomValue(taskStatusAtomFamily(taskId));

/** Subscribe to only the task's model field. Re-renders only when model changes. */
export const useTaskModel = (taskId: string): string | undefined => useAtomValue(taskModelAtomFamily(taskId));

/** Subscribe to the harness's backend-sourced model list (pi); empty for Claude. */
export const useTaskAvailableModels = (taskId: string): ReadonlyArray<ModelOption> =>
  useAtomValue(taskAvailableModelsAtomFamily(taskId));

/** Subscribe to the model_id the switcher should show selected for a backend list (pi). */
export const useTaskSelectedModelId = (taskId: string): string | undefined =>
  useAtomValue(taskSelectedModelIdAtomFamily(taskId));

/** Subscribe to whether the harness sources its model catalog from a backend (pi). */
export const useTaskSourcesBackendModels = (taskId: string): boolean =>
  useAtomValue(taskSourcesBackendModelsAtomFamily(taskId));

export const useTaskIsAutoCompacting = (taskId: string): boolean =>
  useAtomValue(taskIsAutoCompactingAtomFamily(taskId));

/** Subscribe to only the task's `supports_interactive_backchannel` capability. */
export const useTaskSupportsInteractiveBackchannel = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsInteractiveBackchannelAtomFamily(taskId));

/** Subscribe to only the task's `supports_fast_mode` capability. */
export const useTaskSupportsFastMode = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsFastModeAtomFamily(taskId));

/** Subscribe to only the task's `supports_file_attachments` capability. */
export const useTaskSupportsFileAttachments = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsFileAttachmentsAtomFamily(taskId));

/** Subscribe to only the task's `supports_image_input` capability. */
export const useTaskSupportsImageInput = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsImageInputAtomFamily(taskId));

/** Subscribe to only the task's `supports_skills` capability. */
export const useTaskSupportsSkills = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsSkillsAtomFamily(taskId));

/** Subscribe to only the task's `supports_sub_agents` capability. */
export const useTaskSupportsSubAgents = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsSubAgentsAtomFamily(taskId));

/** Subscribe to only the task's `supports_interruption` capability. */
export const useTaskSupportsInterruption = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsInterruptionAtomFamily(taskId));

/** Subscribe to only the task's `supports_file_references` capability. */
export const useTaskSupportsFileReferences = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsFileReferencesAtomFamily(taskId));

/** Subscribe to only the task's `supports_context_reset` capability. */
export const useTaskSupportsContextReset = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsContextResetAtomFamily(taskId));

/** Subscribe to only the task's `supports_compaction` capability. */
export const useTaskSupportsCompaction = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsCompactionAtomFamily(taskId));

/** Subscribe to only the task's `supports_background_tasks` capability. */
export const useTaskSupportsBackgroundTasks = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsBackgroundTasksAtomFamily(taskId));

/** Subscribe to only the task's `supports_session_resume` capability. */
export const useTaskSupportsSessionResume = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsSessionResumeAtomFamily(taskId));

/** Subscribe to only the task's `supports_tool_use_rendering` capability. */
export const useTaskSupportsToolUseRendering = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsToolUseRenderingAtomFamily(taskId));

/** Subscribe to only the task's `supports_chat_interface` capability —
 * the coarse main-panel switch (chat interface vs terminal panel). */
export const useTaskSupportsChatInterface = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsChatInterfaceAtomFamily(taskId));

/** Subscribe to only the task's `supports_model_selection` capability. */
export const useTaskSupportsModelSelection = (taskId: string): boolean | undefined =>
  useAtomValue(taskSupportsModelSelectionAtomFamily(taskId));

/** Subscribe to only the task's `accepts_automated_prompts` field — true
 * only for registered terminal agents whose registration opted in. */
export const useTaskAcceptsAutomatedPrompts = (taskId: string): boolean | undefined =>
  useAtomValue(taskAcceptsAutomatedPromptsAtomFamily(taskId));
