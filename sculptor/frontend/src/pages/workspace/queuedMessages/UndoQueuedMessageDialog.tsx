import { AlertDialog, Button, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { CopyIcon } from "lucide-react";
import { type ReactElement, useState } from "react";

import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";

import { ElementIds } from "../../../api";
import { Toast } from "../../../components/Toast.tsx";
import styles from "./UndoQueuedMessageDialog.module.scss";

type UndoQueuedMessageDialogProps = {
  isOpen: boolean;
  queuedMessageText: string;
  onOpenChange: (open: boolean) => void;
  onOverwrite: () => void;
  onRemove: () => void;
  onKeepQueued: () => void;
  title?: string;
  removeLabel?: string;
  showKeepQueued?: boolean;
};

export const UndoQueuedMessageDialog = ({
  isOpen,
  queuedMessageText,
  onOpenChange,
  onOverwrite,
  onRemove,
  onKeepQueued,
  title = "Edit queued message",
  removeLabel = "Remove",
  showKeepQueued = true,
}: UndoQueuedMessageDialogProps): ReactElement => {
  const [toast, setToast] = useState<ToastContent | null>(null);

  const handleCopy = (): void => {
    navigator.clipboard.writeText(queuedMessageText);
    setToast({ title: "Message copied to clipboard", type: ToastType.SUCCESS });
  };

  return (
    <>
      <AlertDialog.Root open={isOpen} onOpenChange={onOpenChange}>
        <AlertDialog.Content maxWidth="450px" data-testid={ElementIds.UNDO_QUEUED_MESSAGE_DIALOG}>
          <AlertDialog.Title>{title}</AlertDialog.Title>
          <AlertDialog.Description mb="3">You have unsaved text in the chat input.</AlertDialog.Description>
          <Flex align="center" gap="2" className={styles.queuedMessageCard} mb="3">
            <Text className={styles.messageText}>{queuedMessageText}</Text>
            <Tooltip content="Copy to clipboard">
              <IconButton variant="ghost" size="1" className={styles.copyButton} onClick={handleCopy} color="gray">
                <CopyIcon size={14} />
              </IconButton>
            </Tooltip>
          </Flex>
          <AlertDialog.Description>How would you like to proceed?</AlertDialog.Description>
          <Flex gap="3" mt="4" justify="end" wrap="wrap">
            {showKeepQueued && (
              <AlertDialog.Cancel>
                <Button
                  variant="soft"
                  color="gray"
                  onClick={onKeepQueued}
                  data-testid={ElementIds.UNDO_QUEUED_MESSAGE_CANCEL_BUTTON}
                >
                  Keep queued
                </Button>
              </AlertDialog.Cancel>
            )}
            <AlertDialog.Action>
              <Button
                variant="soft"
                color="gray"
                onClick={onRemove}
                data-testid={ElementIds.UNDO_QUEUED_MESSAGE_REMOVE_BUTTON}
              >
                {removeLabel}
              </Button>
            </AlertDialog.Action>
            <AlertDialog.Action>
              <Button
                variant="solid"
                onClick={onOverwrite}
                data-testid={ElementIds.UNDO_QUEUED_MESSAGE_OVERWRITE_BUTTON}
              >
                Overwrite
              </Button>
            </AlertDialog.Action>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>
      <Toast open={!!toast} onOpenChange={(open) => !open && setToast(null)} title={toast?.title} type={toast?.type} />
    </>
  );
};
