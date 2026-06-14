import { useAtomValue } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useState } from "react";

import { EffortLevel, LlmModel, sendWorkspaceAgentMessages, TaskStatus } from "~/api";
import { getModelCapabilities } from "~/common/modelCapabilities.ts";
import { effortAtomFamily, fastModeAtomFamily, modelAtomFamily } from "~/common/state/atoms/draftAgentSettings.ts";
import { defaultEffortLevelAtom, isDefaultFastModeAtom } from "~/common/state/atoms/userConfig.ts";
import { useDraftAttachedFiles } from "~/common/state/hooks/useDraftAttachedFiles.ts";
import { useInterruptAgent } from "~/common/state/hooks/useInterruptAgent.ts";
import { usePromptDraft } from "~/common/state/hooks/usePromptDraft.ts";
import { useTaskDetailWithDefaults } from "~/common/state/hooks/useTaskDetail.ts";
import { useTaskModel, useTaskStatus } from "~/common/state/hooks/useTaskHelpers.ts";

export type ChatMessageSender = {
  draft: string | null;
  setDraft: (value: string | null) => void;
  /** True while the agent is actively running (show stop instead of send, I4). */
  isAgentBusy: boolean;
  isInterrupting: boolean;
  canSend: boolean;
  send: () => Promise<void>;
  interrupt: () => Promise<void>;
  lastSendError: string | null;
};

/**
 * The mobile chat input's submit/draft core. It composes the SAME primitives
 * the desktop ChatInput uses — `usePromptDraft`, the per-task model / fast-mode
 * / effort atoms, `useInterruptAgent`, and the `sendWorkspaceAgentMessages`
 * API — so behavior and persisted state match (I2). It is a plain-text sender:
 * the desktop's TipTap-only pseudo-skill parsing (`/clear`, `/copy`, `/btw`) is
 * intentionally out of scope on mobile.
 */
export const useChatMessageSender = (workspaceID: string, taskID: string): ChatMessageSender => {
  const [draft, setDraft] = usePromptDraft(taskID);
  const [attachedFiles, setAttachedFiles] = useDraftAttachedFiles(taskID);
  const taskModel = useTaskModel(taskID);
  const taskStatus = useTaskStatus(taskID);
  const { isInPlanMode } = useTaskDetailWithDefaults(taskID);

  const storedModel = useAtomValue(modelAtomFamily(taskID));
  const isStoredFastMode = useAtomValue(fastModeAtomFamily(taskID));
  const storedEffort = useAtomValue(effortAtomFamily(taskID));
  const isDefaultFastMode = useAtomValue(isDefaultFastModeAtom);
  const defaultEffortLevel = useAtomValue(defaultEffortLevelAtom);

  const localModel = storedModel ?? (taskModel as LlmModel) ?? LlmModel.CLAUDE_4_OPUS_200K;
  const isFastMode = isStoredFastMode ?? isDefaultFastMode;
  const effort = storedEffort ?? (defaultEffortLevel as EffortLevel) ?? EffortLevel.XHIGH;
  const modelCapabilities = getModelCapabilities(localModel);

  const { interrupt, isInterrupting } = useInterruptAgent(workspaceID, taskID);
  const [lastSendError, setLastSendError] = useState<string | null>(null);

  const isAgentBusy = taskStatus === TaskStatus.RUNNING || taskStatus === TaskStatus.BUILDING;
  const canSend = (draft ?? "").trim().length > 0;

  const send = useCallback(async (): Promise<void> => {
    if (!draft?.trim() || !taskID) return;
    setLastSendError(null);
    try {
      await sendWorkspaceAgentMessages({
        path: { workspace_id: workspaceID, agent_id: taskID },
        body: {
          message: draft.replace(/\u200B/g, "\u00A0").replace(/(\n\n\u00A0)+$/, ""),
          model: localModel,
          files: attachedFiles,
          enter_plan_mode: false,
          exit_plan_mode: isInPlanMode,
          fast_mode: modelCapabilities.supportsFastMode && isFastMode,
          effort,
        },
      });
      posthog.capture("agent.message_sent", {
        model: localModel,
        is_fast_mode: modelCapabilities.supportsFastMode && isFastMode,
        effort,
        has_attached_files: attachedFiles.length > 0,
        is_plan_first: false,
        surface: "mobile",
      });
      setDraft(null);
      setAttachedFiles([]);
    } catch (error) {
      console.error("Failed to send message:", error);
      setLastSendError(error instanceof Error ? error.message : String(error));
    }
  }, [
    draft,
    taskID,
    workspaceID,
    localModel,
    attachedFiles,
    isInPlanMode,
    modelCapabilities,
    isFastMode,
    effort,
    setDraft,
    setAttachedFiles,
  ]);

  return { draft, setDraft, isAgentBusy, isInterrupting, canSend, send, interrupt, lastSendError };
};
