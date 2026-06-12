import { useAtomValue } from "jotai";

import type { CodingAgentTaskView, TaskStatus } from "../../../api";
import {
  taskAtomFamily,
  taskIsAutoCompactingAtomFamily,
  taskModelAtomFamily,
  taskStatusAtomFamily,
  taskSupportsBackgroundTasksAtomFamily,
  taskSupportsCompactionAtomFamily,
  taskSupportsContextResetAtomFamily,
  taskSupportsFastModeAtomFamily,
  taskSupportsFileAttachmentsAtomFamily,
  taskSupportsFileReferencesAtomFamily,
  taskSupportsImageInputAtomFamily,
  taskSupportsInteractiveBackchannelAtomFamily,
  taskSupportsInterruptionAtomFamily,
  taskSupportsSessionResumeAtomFamily,
  taskSupportsSkillsAtomFamily,
  taskSupportsSubAgentsAtomFamily,
  taskSupportsToolUseRenderingAtomFamily,
} from "../atoms/tasks";

export const useTask = (taskId: string): CodingAgentTaskView | null => {
  return useAtomValue(taskAtomFamily(taskId));
};

/** Subscribe to only the task's status field. Re-renders only when status changes. */
export const useTaskStatus = (taskId: string): TaskStatus | undefined => useAtomValue(taskStatusAtomFamily(taskId));

/** Subscribe to only the task's model field. Re-renders only when model changes. */
export const useTaskModel = (taskId: string): string | undefined => useAtomValue(taskModelAtomFamily(taskId));

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
