import { useAtomValue } from "jotai";

import type { CodingAgentTaskView, ModelOption, TaskStatus } from "../../../api";
import {
  agentAcceptsAutomatedPromptsAtomFamily,
  agentAtomFamily,
  agentAvailableModelsAtomFamily,
  agentIsAutoCompactingAtomFamily,
  agentModelAtomFamily,
  agentSelectedModelIdAtomFamily,
  agentSourcesBackendModelsAtomFamily,
  agentStatusAtomFamily,
  agentSupportsBackgroundTasksAtomFamily,
  agentSupportsChatInterfaceAtomFamily,
  agentSupportsCompactionAtomFamily,
  agentSupportsContextResetAtomFamily,
  agentSupportsFastModeAtomFamily,
  agentSupportsFileAttachmentsAtomFamily,
  agentSupportsFileReferencesAtomFamily,
  agentSupportsImageInputAtomFamily,
  agentSupportsInteractiveBackchannelAtomFamily,
  agentSupportsInterruptionAtomFamily,
  agentSupportsModelSelectionAtomFamily,
  agentSupportsSessionResumeAtomFamily,
  agentSupportsSkillsAtomFamily,
  agentSupportsSubAgentsAtomFamily,
  agentSupportsToolUseRenderingAtomFamily,
} from "../atoms/agents";

export const useAgent = (agentId: string): CodingAgentTaskView | null => {
  return useAtomValue(agentAtomFamily(agentId));
};

/** Subscribe to only the agent's status field. Re-renders only when status changes. */
export const useAgentStatusField = (agentId: string): TaskStatus | undefined =>
  useAtomValue(agentStatusAtomFamily(agentId));

/** Subscribe to only the agent's model field. Re-renders only when model changes. */
export const useAgentModel = (agentId: string): string | undefined => useAtomValue(agentModelAtomFamily(agentId));

/** Subscribe to the harness's backend-sourced model list (pi); empty for Claude. */
export const useAgentAvailableModels = (agentId: string): ReadonlyArray<ModelOption> =>
  useAtomValue(agentAvailableModelsAtomFamily(agentId));

/** Subscribe to the model_id the switcher should show selected for a backend list (pi). */
export const useAgentSelectedModelId = (agentId: string): string | undefined =>
  useAtomValue(agentSelectedModelIdAtomFamily(agentId));

/** Subscribe to whether the harness sources its model catalog from a backend (pi). */
export const useAgentSourcesBackendModels = (agentId: string): boolean =>
  useAtomValue(agentSourcesBackendModelsAtomFamily(agentId));

export const useAgentIsAutoCompacting = (agentId: string): boolean =>
  useAtomValue(agentIsAutoCompactingAtomFamily(agentId));

/** Subscribe to only the agent's `supports_interactive_backchannel` capability. */
export const useAgentSupportsInteractiveBackchannel = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsInteractiveBackchannelAtomFamily(agentId));

/** Subscribe to only the agent's `supports_fast_mode` capability. */
export const useAgentSupportsFastMode = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsFastModeAtomFamily(agentId));

/** Subscribe to only the agent's `supports_file_attachments` capability. */
export const useAgentSupportsFileAttachments = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsFileAttachmentsAtomFamily(agentId));

/** Subscribe to only the agent's `supports_image_input` capability. */
export const useAgentSupportsImageInput = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsImageInputAtomFamily(agentId));

/** Subscribe to only the agent's `supports_skills` capability. */
export const useAgentSupportsSkills = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsSkillsAtomFamily(agentId));

/** Subscribe to only the agent's `supports_sub_agents` capability. */
export const useAgentSupportsSubAgents = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsSubAgentsAtomFamily(agentId));

/** Subscribe to only the agent's `supports_interruption` capability. */
export const useAgentSupportsInterruption = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsInterruptionAtomFamily(agentId));

/** Subscribe to only the agent's `supports_file_references` capability. */
export const useAgentSupportsFileReferences = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsFileReferencesAtomFamily(agentId));

/** Subscribe to only the agent's `supports_context_reset` capability. */
export const useAgentSupportsContextReset = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsContextResetAtomFamily(agentId));

/** Subscribe to only the agent's `supports_compaction` capability. */
export const useAgentSupportsCompaction = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsCompactionAtomFamily(agentId));

/** Subscribe to only the agent's `supports_background_tasks` capability. */
export const useAgentSupportsBackgroundTasks = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsBackgroundTasksAtomFamily(agentId));

/** Subscribe to only the agent's `supports_session_resume` capability. */
export const useAgentSupportsSessionResume = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsSessionResumeAtomFamily(agentId));

/** Subscribe to only the agent's `supports_tool_use_rendering` capability. */
export const useAgentSupportsToolUseRendering = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsToolUseRenderingAtomFamily(agentId));

/** Subscribe to only the agent's `supports_chat_interface` capability —
 * the coarse main-panel switch (chat interface vs terminal panel). */
export const useAgentSupportsChatInterface = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsChatInterfaceAtomFamily(agentId));

/** Subscribe to only the agent's `supports_model_selection` capability. */
export const useAgentSupportsModelSelection = (agentId: string): boolean | undefined =>
  useAtomValue(agentSupportsModelSelectionAtomFamily(agentId));

/** Subscribe to only the agent's `accepts_automated_prompts` field — true
 * only for registered terminal agents whose registration opted in. */
export const useAgentAcceptsAutomatedPrompts = (agentId: string): boolean | undefined =>
  useAtomValue(agentAcceptsAutomatedPromptsAtomFamily(agentId));
