import { useSetAtom } from "jotai";
import { useEffect, useMemo } from "react";

import type { AskUserQuestionData, ChatMessage, TaskStatus } from "~/api";
import { LlmModel, sendWorkspaceAgentMessages } from "~/api";
import { useMarkSwitchDataMilestone } from "~/common/perf/workspaceSwitchProfiler.ts";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { chatActionsAtom } from "~/common/state/atoms/chatActions.ts";
import { useTaskChatMessages, useTaskDetailWithDefaults } from "~/common/state/hooks/useTaskDetail";
import { useTaskIsAutoCompacting, useTaskModel, useTaskStatus } from "~/common/state/hooks/useTaskHelpers.ts";
import { useChatSmoothStreaming } from "~/pages/workspace/hooks/useSmoothStreaming.ts";
import {
  useSmoothStreamingOnTaskSwitch,
  useSmoothStreamingViewportObserver,
} from "~/pages/workspace/hooks/useSmoothStreamingViewportObserver.ts";

type UseChatDataArgs = {
  taskID: string;
  workspaceID: string;
  appendTextRef: React.MutableRefObject<((text: string) => void) | null> | undefined;
  insertSkillRef: React.MutableRefObject<((skill: InsertSkillArg) => void) | null> | undefined;
};

export type ChatData = {
  chatMessages: Array<ChatMessage>;
  smoothInProgressChatMessage: ChatMessage | null;
  isStreaming: boolean;
  workingUserMessageId: string | null;
  queuedChatMessages: Array<ChatMessage>;
  taskStatus: TaskStatus | undefined;
  taskModel: string | undefined;
  isAutoCompacting: boolean;
  pendingUserQuestion: AskUserQuestionData | null;
  pendingBackgroundTaskCount: number;
  bottomSentinelRef: React.MutableRefObject<HTMLDivElement | null>;
};

export const useChatData = ({ taskID, workspaceID, appendTextRef, insertSkillRef }: UseChatDataArgs): ChatData => {
  const {
    chatMessages: rawChatMessages,
    inProgressChatMessage,
    workingUserMessageId,
    queuedChatMessages,
    pendingBackgroundTaskIds,
  } = useTaskChatMessages(taskID);
  const { pendingUserQuestion } = useTaskDetailWithDefaults(taskID);
  const smoothInProgressChatMessage = useChatSmoothStreaming(inProgressChatMessage);
  const chatMessages = useMemo(() => {
    // Only substitute the smooth message when its ID matches the current
    // in-progress message. There is a one-render-cycle window where the smooth
    // hook still holds the previous message's state (the useEffect that updates
    // it fires after paint). During that window the IDs diverge; falling back to
    // rawChatMessages prevents the stale smooth message from hiding the new
    // in-progress message or creating a duplicate-ID entry in the list.
    if (smoothInProgressChatMessage && smoothInProgressChatMessage.id === inProgressChatMessage?.id) {
      return [...rawChatMessages.slice(0, -1), smoothInProgressChatMessage];
    }
    return rawChatMessages;
  }, [rawChatMessages, smoothInProgressChatMessage, inProgressChatMessage]);
  const isStreaming = smoothInProgressChatMessage !== null;

  useMarkSwitchDataMilestone("chat-loaded", workspaceID, rawChatMessages.length > 0);

  const taskStatus = useTaskStatus(taskID);
  const taskModel = useTaskModel(taskID);
  const isAutoCompacting = useTaskIsAutoCompacting(taskID);
  const setChatActions = useSetAtom(chatActionsAtom);
  const bottomSentinelRef = useSmoothStreamingViewportObserver();
  useSmoothStreamingOnTaskSwitch(taskID, bottomSentinelRef);

  // Bind the action closures whenever taskID/model/refs change. No cleanup
  // here — a re-run just overwrites the previous closures, and the unmount
  // teardown lives in its own effect below.
  useEffect(() => {
    setChatActions((prev) => ({
      ...prev,
      appendText: (text: string): void => {
        appendTextRef?.current?.(text);
      },
      insertSkill: (skill: InsertSkillArg): void => {
        insertSkillRef?.current?.(skill);
      },
      sendMessage: async (message: string): Promise<void> => {
        if (!taskID) return;
        await sendWorkspaceAgentMessages({
          path: { workspace_id: workspaceID, agent_id: taskID },
          body: { message, model: (taskModel as LlmModel) || LlmModel.CLAUDE_4_OPUS_200K },
        });
      },
    }));
  }, [setChatActions, appendTextRef, insertSkillRef, workspaceID, taskID, taskModel]);

  // Track `isDisabled` separately so a queue-length change doesn't tear down
  // and re-bind the action closures on every queued-message mutation.
  useEffect(() => {
    const isDisabled = queuedChatMessages.length > 0;
    setChatActions((prev) => ({ ...prev, isDisabled }));
  }, [setChatActions, queuedChatMessages.length]);

  // On unmount, null the closures so consumers like SkillsPanel don't hold
  // stale references to a torn-down editor or task, and flip isDisabled back
  // to true so they treat the chat as unavailable.
  useEffect(() => {
    return (): void => {
      setChatActions({ appendText: null, insertSkill: null, sendMessage: null, isDisabled: true });
    };
  }, [setChatActions]);

  return {
    chatMessages,
    smoothInProgressChatMessage,
    isStreaming,
    workingUserMessageId,
    queuedChatMessages,
    taskStatus,
    taskModel,
    isAutoCompacting,
    pendingUserQuestion,
    pendingBackgroundTaskCount: pendingBackgroundTaskIds.length,
    bottomSentinelRef,
  };
};
