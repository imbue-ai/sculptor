import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo } from "react";

import type { AskUserQuestionData, ChatMessage, TaskStatus } from "~/api";
import { LlmModel, sendWorkspaceAgentMessages } from "~/api";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { chatActionsAtom } from "~/common/state/atoms/chatActions.ts";
import { useAgentChatMessages, useAgentDetailWithDefaults } from "~/common/state/hooks/useAgentDetail";
import { useAgentIsAutoCompacting, useAgentModel, useAgentStatusField } from "~/common/state/hooks/useAgentHelpers.ts";
import { useChatSmoothStreaming } from "~/pages/workspace/chat/hooks/useSmoothStreaming.ts";
import {
  useSmoothStreamingOnAgentSwitch,
  useSmoothStreamingViewportObserver,
} from "~/pages/workspace/chat/hooks/useSmoothStreamingViewportObserver.ts";
import { activeChatAgentIdAtomFamily } from "~/pages/workspace/panels/workspaceAgentActions.ts";

type UseChatDataArgs = {
  agentId: string;
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
  agentStatus: TaskStatus | undefined;
  agentModel: string | undefined;
  isAutoCompacting: boolean;
  pendingUserQuestion: AskUserQuestionData | null;
  pendingBackgroundTaskCount: number;
  bottomSentinelRef: React.MutableRefObject<HTMLDivElement | null>;
};

export const useChatData = ({ agentId, workspaceID, appendTextRef, insertSkillRef }: UseChatDataArgs): ChatData => {
  const {
    chatMessages: rawChatMessages,
    inProgressChatMessage,
    workingUserMessageId,
    queuedChatMessages,
    pendingBackgroundTaskIds,
  } = useAgentChatMessages(agentId);
  const { pendingUserQuestion } = useAgentDetailWithDefaults(agentId);
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

  const agentStatus = useAgentStatusField(agentId);
  const agentModel = useAgentModel(agentId);
  const isAutoCompacting = useAgentIsAutoCompacting(agentId);
  const setChatActions = useSetAtom(chatActionsAtom);
  const bottomSentinelRef = useSmoothStreamingViewportObserver();
  useSmoothStreamingOnAgentSwitch(agentId, bottomSentinelRef);

  // `chatActionsAtom` is a single slot shared by workspace-scoped consumers
  // (SkillsPanel, ActionsPanel, PrButton, the command palette), but several
  // chat panels can be mounted at once — one per placed agent panel. Only the
  // panel for the workspace's active chat agent registers its closures: that
  // is the same resolution the consumers gate on, so actions reach the agent
  // they display as their target instead of whichever panel bound last, and
  // one panel unmounting cannot strand a surviving panel's registration.
  const isChatActionsOwner = useAtomValue(activeChatAgentIdAtomFamily(workspaceID)) === agentId;

  // Bind the action closures whenever ownership/agentId/model/refs change. No
  // cleanup here — a re-run just overwrites the previous closures, and the
  // teardown lives in its own ownership-scoped effect below.
  useEffect(() => {
    if (!isChatActionsOwner) return;
    setChatActions((prev) => ({
      ...prev,
      appendText: (text: string): void => {
        appendTextRef?.current?.(text);
      },
      insertSkill: (skill: InsertSkillArg): void => {
        insertSkillRef?.current?.(skill);
      },
      sendMessage: async (message: string): Promise<void> => {
        if (!agentId) return;
        await sendWorkspaceAgentMessages({
          path: { workspace_id: workspaceID, agent_id: agentId },
          body: { message, model: (agentModel as LlmModel) || LlmModel.CLAUDE_4_OPUS_200K },
        });
      },
    }));
  }, [setChatActions, isChatActionsOwner, appendTextRef, insertSkillRef, workspaceID, agentId, agentModel]);

  // Track `isDisabled` separately so a queue-length change doesn't tear down
  // and re-bind the action closures on every queued-message mutation.
  useEffect(() => {
    if (!isChatActionsOwner) return;
    const isDisabled = queuedChatMessages.length > 0;
    setChatActions((prev) => ({ ...prev, isDisabled }));
  }, [setChatActions, isChatActionsOwner, queuedChatMessages.length]);

  // When this panel stops owning the slot (its agent is no longer the active
  // chat agent, or the panel unmounts while owning), null the closures so
  // consumers don't hold stale references to a torn-down editor or agent, and
  // flip isDisabled back to true so they treat the chat as unavailable. The
  // cleanup is registered only while owning, so a non-owner unmounting never
  // wipes the owner's registration; on an ownership hand-off React runs this
  // cleanup before the new owner's bind effect, which then re-registers.
  useEffect(() => {
    if (!isChatActionsOwner) return undefined;
    return (): void => {
      setChatActions({ appendText: null, insertSkill: null, sendMessage: null, isDisabled: true });
    };
  }, [setChatActions, isChatActionsOwner]);

  return {
    chatMessages,
    smoothInProgressChatMessage,
    isStreaming,
    workingUserMessageId,
    queuedChatMessages,
    agentStatus,
    agentModel,
    isAutoCompacting,
    pendingUserQuestion,
    pendingBackgroundTaskCount: pendingBackgroundTaskIds.length,
    bottomSentinelRef,
  };
};
