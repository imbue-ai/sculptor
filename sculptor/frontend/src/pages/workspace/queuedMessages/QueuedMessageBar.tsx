import { Flex, IconButton, Spinner, Text, Tooltip } from "@radix-ui/themes";
import { ArrowUpIcon, PencilIcon, Trash2Icon } from "lucide-react";
import { type ReactElement, useCallback, useState } from "react";

import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";

import type { ChatMessage, FileBlock, TextBlock } from "../../../api";
import { deleteWorkspaceAgentMessage, ElementIds } from "../../../api";
import { useDraftAttachedFiles } from "../../../common/state/hooks/useDraftAttachedFiles.ts";
import { useInterruptAgent } from "../../../common/state/hooks/useInterruptAgent.ts";
import { usePromptDraft } from "../../../common/state/hooks/usePromptDraft.ts";
import { useTaskSupportsInterruption } from "../../../common/state/hooks/useTaskHelpers.ts";
import { Toast } from "../../../components/Toast.tsx";
import { getMetaKey } from "../../../electron/platform.ts";
import { CapabilityGate } from "../chatAlpha/CapabilityGate.tsx";
import { useChatTask } from "../chatAlpha/ChatTaskContext.tsx";
import type { BlockUnion } from "../utils/blockGuards.ts";
import { isFileBlock, isTextBlock } from "../utils/blockGuards.ts";
import { stripHtml } from "../utils/stripHtml.ts";
import styles from "./QueuedMessageBar.module.scss";

export type EditConflictData = {
  rawTextContent: string;
  plainTextContent: string;
  fileSources: Array<string>;
};

type QueuedMessageBarProps = {
  message: ChatMessage;
  onEditConflict: (data: EditConflictData) => void;
};

export const QueuedMessageBar = ({ message, onEditConflict }: QueuedMessageBarProps): ReactElement => {
  // The owning chat panel's agent — `message.id` belongs to that agent's
  // queue, so delete/interrupt must target it rather than the route's agent.
  const { workspaceId: workspaceID, taskId: taskID } = useChatTask();
  const [toast, setToast] = useState<ToastContent | null>(null);
  const {
    isInterrupting,
    interrupt: handleInterruptAndSend,
    toast: interruptToast,
    setToast: setInterruptToast,
  } = useInterruptAgent(workspaceID, taskID);
  const [promptDraft, setPromptDraft] = usePromptDraft(taskID);
  const [, setAttachedFiles] = useDraftAttachedFiles(taskID);

  // Stable callbacks so the memoized <Toast> instances below bail out instead
  // of re-rendering on every unrelated parent render. (SCU-1455)
  const handleToastOpenChange = useCallback((open: boolean) => {
    if (!open) setToast(null);
  }, []);
  const handleInterruptToastOpenChange = useCallback(
    (open: boolean) => {
      if (!open) setInterruptToast(null);
    },
    [setInterruptToast],
  );
  // Interrupt-and-send halts the running turn to promote this queued message.
  // A harness that can't be interrupted (pi) hides the button entirely; the
  // message simply stays queued until the turn ends. `?? true` keeps it shown
  // until the task loads — Claude reports true, pi false.
  const canInterrupt = useTaskSupportsInterruption(taskID) ?? true;

  const textBlocks = message.content.filter((block: BlockUnion): block is TextBlock => isTextBlock(block));
  const fileBlocks = message.content.filter((block: BlockUnion): block is FileBlock => isFileBlock(block));

  const rawTextContent = textBlocks.map((block) => block.text).join("");
  const plainTextContent = stripHtml(rawTextContent);
  const fileSources = fileBlocks.map((block) => block.source);

  const handleDelete = async (): Promise<void> => {
    try {
      await deleteWorkspaceAgentMessage({
        path: { workspace_id: workspaceID, agent_id: taskID, message_id: message.id },
      });
    } catch (error) {
      console.error("Failed to delete queued message:", error);
      setToast({ title: "Failed to remove queued message", type: ToastType.ERROR });
    }
  };

  const handleEdit = async (): Promise<void> => {
    // The TipTap editor serialises empty paragraphs as ZWSP (\u200B).
    // Strip it before checking whether the editor has real content, since
    // ZWSP is invisible and is NOT removed by String.trim().
    const hasRealDraft = !!promptDraft?.replace(/\u200B/g, "").trim();
    if (hasRealDraft) {
      // Un-queue before showing dialog to prevent the message from being
      // promoted while the user is choosing what to do.  The dialog is rendered
      // by AlphaChatInterface (our parent) so it survives this component
      // unmounting.
      await handleDelete();
      onEditConflict({ rawTextContent, plainTextContent, fileSources });
    } else {
      // Editor is empty — directly move content
      setPromptDraft(rawTextContent);
      if (fileSources.length > 0) {
        setAttachedFiles(fileSources);
      }
      await handleDelete();
    }
  };

  return (
    <>
      <Flex align="center" gap="3" className={styles.queuedMessageBar} data-testid={ElementIds.QUEUED_MESSAGE_BAR}>
        <Text className={styles.messageContent}>{plainTextContent}</Text>
        <Flex align="center" gap="2" flexShrink="0">
          <Flex align="center" gap="2" className={styles.hoverActions}>
            <Tooltip content="Remove queued message">
              <IconButton
                variant="ghost"
                color="gray"
                size="1"
                onClick={handleDelete}
                data-testid={ElementIds.QUEUED_MESSAGE_CANCEL_BUTTON}
                aria-label="Remove queued message"
              >
                <Trash2Icon size={14} />
              </IconButton>
            </Tooltip>
            <Tooltip content="Edit message">
              <IconButton
                variant="ghost"
                color="gray"
                size="1"
                onClick={handleEdit}
                data-testid={ElementIds.QUEUED_MESSAGE_EDIT_BUTTON}
                aria-label="Edit message"
              >
                <PencilIcon size={14} />
              </IconButton>
            </Tooltip>
          </Flex>
          <CapabilityGate
            capabilityValue={canInterrupt}
            elementId={ElementIds.CAPABILITY_DISABLED_QUEUED_INTERRUPT}
            disabledIcon={<ArrowUpIcon size={14} />}
            size="1"
            variant="solid"
            color="gray"
          >
            <Tooltip content={isInterrupting ? "Interrupting..." : `${getMetaKey()}⇧⏎ Interrupt and send`}>
              <IconButton
                variant="solid"
                color="gray"
                size="1"
                onClick={handleInterruptAndSend}
                disabled={isInterrupting}
                data-testid={ElementIds.QUEUED_MESSAGE_SEND_BUTTON}
                aria-label="Interrupt and send"
              >
                {isInterrupting ? <Spinner size="1" /> : <ArrowUpIcon size={14} />}
              </IconButton>
            </Tooltip>
          </CapabilityGate>
        </Flex>
      </Flex>
      <Toast open={!!toast} onOpenChange={handleToastOpenChange} title={toast?.title} type={toast?.type} />
      <Toast
        open={!!interruptToast}
        onOpenChange={handleInterruptToastOpenChange}
        title={interruptToast?.title}
        type={interruptToast?.type}
      />
    </>
  );
};
